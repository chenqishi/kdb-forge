#!/usr/bin/env python3
"""Read-only online verification of an ES7 dump against ES8 staging indices.

The script is intentionally a verifier only.  It does not create/delete indices,
refresh, update aliases, or write documents.  A deterministic prefix sample is
stratified by provider and index.  Three-way comparison against the local dump
distinguishes changes in the live source from a failed snapshot import.  Counts
and mappings cover the entire selected scope, while costly ES7 exact vector
queries are limited to four fields per provider plus one joint-index probe.

Typical use (after every local import checkpoint is ``import_done``)::

    python scripts/compare_es7_es8_online.py \\
      --source-config /path/to/es7-readonly.json \\
      --target-config config/config_es_runtime.local.json \\
      --dump-dir migration_runs/local_dump_20261001/data \\
      --shard-plan migration_runs/local_dump_20261001/data/shard_plan_1g.json \\
      --sample-size 400 \\
      --report migration_runs/local_dump_20261001/data/online_compare.json

The source config must be a read-only ES7 endpoint config with ``hosts``,
``username`` and ``password``.  A config containing a ``providers`` mapping is
also accepted; ``source``/``es7`` is preferred, otherwise its first provider is
used.  Credentials and document contents are never written to the report.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import heapq
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Reuse the migration HTTP client and physical target naming.  The import has no
# side effects and this verifier never calls the mutation methods in that file.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from migrate_es7_to_es8 import ESHttp, index_provider, staged_name  # noqa: E402

VECTOR_FIELDS = (
    ("title_embedding", "root"),
    ("content_embedding", "root"),
    ("indexes.embedding", "nested"),
    ("image_indexes.embedding", "nested"),
)
MAX_MGET = 100
TOP_K = 10
FLOAT_TOLERANCE = 1e-6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def extract_endpoint(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept a direct endpoint or a provider wrapper without exposing values."""
    if config.get("hosts") or config.get("host"):
        return config
    providers = config.get("providers")
    if isinstance(providers, Mapping) and providers:
        for name in ("source", "es7", "legacy", "serverless", "paas"):
            if isinstance(providers.get(name), Mapping):
                return providers[name]
        first = next(iter(providers.values()))
        if isinstance(first, Mapping):
            return first
    raise ValueError("source config must contain hosts/host or a non-empty providers mapping")


def target_endpoints(config: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    providers = config.get("providers")
    if not isinstance(providers, Mapping):
        raise ValueError("target config must contain providers.serverless and providers.paas")
    result: Dict[str, Mapping[str, Any]] = {}
    for key, value in providers.items():
        if not isinstance(value, Mapping):
            continue
        name = str(key).lower().replace("pass", "paas").replace("server-less", "serverless")
        result[name] = value
    missing = [x for x in ("serverless", "paas") if x not in result]
    if missing:
        raise ValueError(f"target config missing providers: {', '.join(missing)}")
    return result


def total_hits(body: Mapping[str, Any]) -> int:
    value = body.get("hits", {}).get("total", 0)
    return int(value.get("value", 0) if isinstance(value, Mapping) else value or 0)


def response_hits(body: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return list(body.get("hits", {}).get("hits", []) or [])


def parse_vector(value: Any, dims: int = 1024) -> Optional[List[float]]:
    if not isinstance(value, list) or len(value) != dims:
        return None
    try:
        result = [float(x) for x in value]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in result):
        return None
    return result


def get_path(source: Mapping[str, Any], field: str) -> Any:
    if "." not in field:
        return source.get(field)
    parent, leaf = field.split(".", 1)
    value = source.get(parent)
    if not isinstance(value, list):
        return None
    return [item.get(leaf) for item in value if isinstance(item, Mapping) and leaf in item]


def first_vector(source: Mapping[str, Any], field: str) -> Optional[List[float]]:
    value = get_path(source, field)
    if "." not in field:
        return parse_vector(value)
    if isinstance(value, list):
        for item in value:
            vector = parse_vector(item)
            if vector is not None:
                return vector
    return None


def iter_dump_records(path: Path) -> Iterable[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid dump JSON {path}:{line_number}: {exc}") from exc
            if isinstance(record, dict) and "_id" in record and isinstance(record.get("_source"), dict):
                yield record


def deterministic_sample(states: Sequence[Mapping[str, Any]], quota: int, seed: str) -> List[Dict[str, Any]]:
    """Select the lowest stable hashes, retaining full source only for samples."""
    heap: List[Tuple[int, str, Dict[str, Any]]] = []
    for state in states:
        path = Path(str(state.get("file", "")))
        if not path.exists():
            raise RuntimeError(f"local dump missing: {path}")
        index = str(state["source_index"])
        for record in iter_dump_records(path):
            identity = f"{seed}\0{index}\0{record['_id']}".encode("utf-8")
            score = int(hashlib.sha256(identity).hexdigest()[:16], 16)
            candidate = (-score, index + "\0" + str(record["_id"]), {**record, "__index": index})
            if len(heap) < quota:
                heapq.heappush(heap, candidate)
            elif candidate[:2] > heap[0][:2]:
                heapq.heapreplace(heap, candidate)
    return [item[2] for item in sorted(heap, key=lambda x: (x[2]["__index"], str(x[2]["_id"]))) ]


def stratified_prefix_sample(states: Sequence[Mapping[str, Any]], quota: int, seed: str) -> List[Dict[str, Any]]:
    """Cover every index without parsing all multi-GB dumps.

    This is explicitly a deterministic prefix sample, not a random sample of
    the complete population. The seed controls quota redistribution order.
    """
    if quota < len(states):
        raise ValueError(f"sample quota {quota} cannot cover {len(states)} indices")
    capacities = {str(s["source_index"]): int(s.get("docs_exported", 0)) for s in states}
    if any(n <= 0 for n in capacities.values()):
        raise ValueError("selected indices must have nonempty exported dumps")
    allocations = {index: 1 for index in capacities}
    order = sorted(capacities, key=lambda name: hashlib.sha256((seed + name).encode()).digest())
    remaining = min(quota, sum(capacities.values())) - len(allocations)
    while remaining:
        changed = False
        for index in order:
            if remaining and allocations[index] < capacities[index]:
                allocations[index] += 1
                remaining -= 1
                changed = True
        if not changed:
            break
    records: List[Dict[str, Any]] = []
    for state in states:
        index = str(state["source_index"])
        path = Path(str(state["file"]))
        found = []
        for record in iter_dump_records(path):
            found.append({**record, "__index": index})
            if len(found) == allocations[index]:
                break
        if len(found) != allocations[index]:
            raise RuntimeError(f"dump prefix shorter than expected: {index}")
        records.extend(found)
    return records


def chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def mget(client: ESHttp, index: str, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for part in chunks(list(ids), MAX_MGET):
        body = client.json("POST", f"/{index}/_mget", json={"docs": [{"_id": str(x)} for x in part]})
        for doc in body.get("docs", []) or []:
            if doc.get("error"):
                raise RuntimeError(f"mget item failed: index={index}, id={doc.get('_id')}, type={(doc.get('error') or {}).get('type')}")
            if doc.get("found"):
                result[str(doc.get("_id"))] = doc
    return result


def compare_values(left: Any, right: Any, path: str = "", mismatches: Optional[List[str]] = None) -> Tuple[bool, float]:
    mismatches = mismatches if mismatches is not None else []
    max_diff = 0.0
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool):
        diff = abs(float(left) - float(right))
        max_diff = diff
        if diff > FLOAT_TOLERANCE:
            mismatches.append(path or "<root>")
        return diff <= FLOAT_TOLERANCE, max_diff
    if type(left) is not type(right):
        # JSON integers/floats may be decoded with different numeric classes;
        # the numeric branch above already handles those.  Everything else is a
        # real shape mismatch.
        mismatches.append(path or "<root>")
        return False, max_diff
    if isinstance(left, Mapping):
        ok = True
        keys = set(left) | set(right)
        for key in sorted(keys):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                mismatches.append(child)
                ok = False
                continue
            same, diff = compare_values(left[key], right[key], child, mismatches)
            ok = ok and same
            max_diff = max(max_diff, diff)
        return ok, max_diff
    if isinstance(left, list):
        ok = len(left) == len(right)
        if not ok:
            mismatches.append(path + ".length")
        for offset, (a, b) in enumerate(zip(left, right)):
            same, diff = compare_values(a, b, f"{path}[{offset}]", mismatches)
            ok = ok and same
            max_diff = max(max_diff, diff)
        return ok, max_diff
    if left != right:
        mismatches.append(path or "<root>")
        return False, max_diff
    return True, max_diff


def props_from_mapping(body: Mapping[str, Any], index: str) -> Mapping[str, Any]:
    entry = body.get(index) or (next(iter(body.values())) if body else {})
    return (entry.get("mappings") or {}).get("properties") or {}


def vector_mapping(props: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    if "." not in field:
        value = props.get(field, {})
        return value if isinstance(value, Mapping) else {}
    parent, leaf = field.split(".", 1)
    parent_map = props.get(parent, {})
    if not isinstance(parent_map, Mapping):
        return {}
    nested_props = parent_map.get("properties", {})
    value = nested_props.get(leaf, {}) if isinstance(nested_props, Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def vector_mapping_check(source_props: Mapping[str, Any], target_props: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for field, _kind in VECTOR_FIELDS:
        old = vector_mapping(source_props, field)
        new = vector_mapping(target_props, field)
        target_ok = (
            new.get("type") == "dense_vector"
            and int(new.get("dims", -1)) == 1024
            and new.get("index") is True
            and new.get("similarity") == "cosine"
            and (new.get("index_options") or {}).get("type") == "hnsw"
            and ("." not in field or target_props.get(field.split(".", 1)[0], {}).get("type") == "nested")
        )
        result[field] = {
            "source_type": old.get("type"),
            "source_dims": old.get("dims"),
            "source_parent_type": source_props.get(field.split(".", 1)[0], {}).get("type") if "." in field else None,
            "target_type": new.get("type"),
            "target_dims": new.get("dims"),
            "target_index": new.get("index"),
            "target_similarity": new.get("similarity"),
            "target_index_options": new.get("index_options"),
            "target_hnsw_ok": target_ok,
        }
    return result


def count_index(client: ESHttp, index: str) -> int:
    body = client.json("POST", f"/{index}/_count", json={"query": {"match_all": {}}})
    return int(body.get("count", 0))


def del_buckets(client: ESHttp, index: str) -> Dict[str, int]:
    body = client.json(
        "POST",
        f"/{index}/_search",
        json={"size": 0, "track_total_hits": False, "aggs": {"del": {"terms": {"field": "del_flag", "size": 10}}}},
    )
    buckets = (body.get("aggregations", {}).get("del", {}) or {}).get("buckets", [])
    return {str(item.get("key")): int(item.get("doc_count", 0)) for item in buckets if isinstance(item, Mapping)}


def query_ids(client: ESHttp, index: str, query: Mapping[str, Any], size: int = TOP_K) -> Tuple[List[str], List[float], Optional[str]]:
    try:
        body = client.json("POST", f"/{index}/_search", json={"size": size, "track_total_hits": False, "_source": False, "query": query})
        hits = response_hits(body)
        return [str(hit.get("_id")) for hit in hits], [float(hit.get("_score") or 0.0) for hit in hits], None
    except Exception as exc:  # Query incompatibility is part of the report, not a write failure.
        return [], [], f"{type(exc).__name__}: {str(exc)[:300]}"


def overlap_result(source_ids: Sequence[str], target_ids: Sequence[str]) -> Dict[str, Any]:
    old_set, new_set = set(source_ids), set(target_ids)
    overlap = old_set & new_set
    return {
        "source_ids": list(source_ids),
        "target_ids": list(target_ids),
        "overlap": len(overlap),
        "source_count": len(old_set),
        "target_count": len(new_set),
        "overlap_fraction_source": round(len(overlap) / max(1, len(old_set)), 4),
        "overlap_fraction_target": round(len(overlap) / max(1, len(new_set)), 4),
        "top1_same": bool(source_ids and target_ids and source_ids[0] == target_ids[0]),
    }


def keyword_probe(record: Mapping[str, Any]) -> Optional[Tuple[str, Any]]:
    source = record.get("_source") or {}
    if not isinstance(source, Mapping):
        return None
    for field in ("keywords", "title", "content", "question", "text"):
        value = source.get(field)
        if isinstance(value, list):
            value = next((x for x in value if isinstance(x, str) and x.strip()), None)
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if field != "keywords":
            # Keep the query bounded and avoid punctuation-only/URL probes.
            parts = [x for x in re.split(r"[^\w\u3400-\u9fff-]+", value) if len(x) >= 2]
            value = parts[0] if parts else value[:32]
        return field, value[:128]
    return None


def knn_query(field: str, kind: str, vector: Sequence[float], native: bool) -> Dict[str, Any]:
    if native:
        clause: Dict[str, Any] = {"field": field, "query_vector": list(vector), "k": TOP_K, "num_candidates": max(100, TOP_K * 10)}
        if kind == "nested":
            return {"nested": {"path": field.split(".", 1)[0], "score_mode": "max", "query": {"knn": clause}}}
        return {"knn": clause}
    script = {
        "source": f"cosineSimilarity(params.query_vector, '{field}') + 1.0",
        "params": {"query_vector": list(vector)},
    }
    if kind == "nested":
        nested_query = {"script_score": {"query": {"exists": {"field": field}}, "script": script}}
        return {"nested": {"path": field.split(".", 1)[0], "score_mode": "max", "query": nested_query}}
    return {"script_score": {"query": {"exists": {"field": field}}, "script": script}}


def run_keyword_probe(source: ESHttp, target: ESHttp, source_index: str, target_index: str, record: Mapping[str, Any]) -> Dict[str, Any]:
    probe = keyword_probe(record)
    result: Dict[str, Any] = {"status": "skipped", "index": source_index}
    if not probe:
        return result
    field, value = probe
    query = {"term": {field: value}} if field == "keywords" else {"match": {field: value}}
    old_ids, _old_scores, old_error = query_ids(source, source_index, query)
    new_ids, _new_scores, new_error = query_ids(target, target_index, query)
    result.update({"status": "ok" if not old_error and not new_error else "error", "field": field, "query_sha256": sha256_json(query), "query_type": next(iter(query)), "source_error": old_error, "target_error": new_error})
    result.update(overlap_result(old_ids, new_ids))
    return result


def run_knn_probe(source: ESHttp, target: ESHttp, source_index: str, target_index: str, record: Mapping[str, Any], field: str, kind: str) -> Dict[str, Any]:
    vector = first_vector(record.get("_source") or {}, field)
    result: Dict[str, Any] = {"status": "skipped", "index": source_index, "field": field, "kind": kind}
    if vector is None:
        return result
    old_ids, old_scores, old_error = query_ids(source, source_index, knn_query(field, kind, vector, native=False))
    new_ids, new_scores, new_error = query_ids(target, target_index, knn_query(field, kind, vector, native=True))
    result.update({"status": "ok" if not old_error and not new_error else "error", "query_vector_dims": len(vector), "query_vector_sha256": sha256_json(vector), "source_error": old_error, "target_error": new_error, "source_scores": [round(x, 8) for x in old_scores], "target_scores": [round(x, 8) for x in new_scores]})
    result.update(overlap_result(old_ids, new_ids))
    return result


def select_states(dump_dir: Path, requested: Sequence[str], shard_plan: Optional[Path] = None) -> List[Dict[str, Any]]:
    manifest = load_json(dump_dir / "manifest.json")
    selected = {str(item.get("source_index")) for item in manifest.get("indices", []) if item.get("source_index")}
    if shard_plan is not None:
        plan = load_json(shard_plan)
        planned = {str(item["source_index"]) for item in plan.get("selected", [])}
        if not planned or len(planned) != int(plan.get("selected_count", len(planned))):
            raise ValueError("invalid or duplicate shard-plan selected indices")
        if planned - selected:
            raise ValueError(f"shard-plan indices missing from manifest: {sorted(planned - selected)}")
        selected = planned
    if requested:
        unknown = set(requested) - selected
        if unknown:
            raise ValueError(f"requested indices outside migration scope: {sorted(unknown)}")
        selected = set(requested)
    states: List[Dict[str, Any]] = []
    found: set[str] = set()
    incomplete: List[str] = []
    for path in sorted((dump_dir / "states").glob("*.json")):
        state = load_json(path)
        if state.get("source_index") not in selected:
            continue
        index = str(state["source_index"])
        if index in found:
            raise ValueError(f"duplicate checkpoint for index: {index}")
        found.add(index)
        target_index = str(state.get("target_index") or "")
        if (state.get("import_status") != "done" or state.get("status") != "import_done"
                or not target_index.startswith(index + "__v817_")
                or int(state.get("docs_imported", -1)) != int(state.get("docs_exported", -2))
                or int(state.get("target_count", -1)) != int(state.get("docs_exported", -2))):
            incomplete.append(index)
        states.append(state)
    if selected - found or incomplete:
        raise RuntimeError(f"all selected imports must be complete; missing={sorted(selected - found)}, incomplete={sorted(incomplete)}")
    return states


def comparison(left: Any, right: Any) -> Dict[str, Any]:
    paths: List[str] = []
    equal = left is not None and right is not None
    maximum = 0.0
    if equal:
        equal, maximum = compare_values(left, right, mismatches=paths)
    return {"equal": equal, "max_numeric_diff": maximum, "mismatch_paths": paths[:10]}


def without_vectors(source: Any) -> Any:
    if not isinstance(source, Mapping):
        return source
    result = {k: v for k, v in source.items() if k not in ("title_embedding", "content_embedding")}
    for parent in ("indexes", "image_indexes"):
        if isinstance(result.get(parent), list):
            result[parent] = [{k: v for k, v in item.items() if k != "embedding"} if isinstance(item, Mapping) else item
                              for item in result[parent]]
    return result


def read_root_vector_values(target: ESHttp, index: str, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Retrieve indexed root vectors even when Serverless filters _source."""
    result: Dict[str, Dict[str, Any]] = {}
    for part in chunks(list(ids), MAX_MGET):
        body = target.json("POST", f"/{index}/_search", json={
            "size": len(part), "_source": False, "query": {"ids": {"values": list(part)}},
            "docvalue_fields": ["title_embedding", "content_embedding"],
        })
        if body.get("timed_out") or (body.get("_shards") or {}).get("failed", 0):
            raise RuntimeError("vector doc-values retrieval returned partial results")
        for hit in response_hits(body):
            values = {}
            for field in ("title_embedding", "content_embedding"):
                value = (hit.get("fields") or {}).get(field)
                if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
                    value = value[0]
                if parse_vector(value) is not None:
                    values[field] = value
            result[str(hit["_id"])] = values
    return result


def compare_three_way(record: Mapping[str, Any], old_source: Any, new_source: Any,
                      indexed_vectors: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    local = record["_source"]
    reconstructed = dict(new_source) if isinstance(new_source, Mapping) else new_source
    restored_fields = []
    if isinstance(reconstructed, dict):
        for field, value in (indexed_vectors or {}).items():
            if field not in reconstructed:
                reconstructed[field] = value
                restored_fields.append(field)
    raw_snapshot = comparison(local, new_source)
    raw_online = comparison(old_source, new_source)
    snapshot = comparison(local, reconstructed)
    source_snapshot = comparison(local, old_source)
    online = comparison(old_source, reconstructed)
    if not snapshot["equal"]:
        classification = "target_missing" if new_source is None else "target_differs_from_export"
    elif not source_snapshot["equal"]:
        classification = "source_deleted_since_export" if old_source is None else "source_changed_since_export"
    else:
        classification = "vector_filtered_snapshot_equal" if restored_fields else "unchanged_equal"
    vector_checks = {}
    for field, _ in VECTOR_FIELDS:
        expected, retrieved = get_path(local, field), get_path(reconstructed or {}, field)
        check = comparison(expected, retrieved) if expected is not None or retrieved is not None else {"equal": True, "max_numeric_diff": 0.0, "mismatch_paths": []}
        vector_checks[field] = {**check, "retrieval": "doc_values" if field in restored_fields else "_source",
                                "expected_present": expected is not None, "retrieved_present": retrieved is not None}
    return {
        "_id": str(record["_id"]), "source_found": old_source is not None,
        "target_found": new_source is not None, "classification": classification,
        "snapshot_vs_target": snapshot, "snapshot_vs_source": source_snapshot,
        "source_vs_target": online,
        "raw_snapshot_vs_target": raw_snapshot, "raw_source_vs_target": raw_online,
        "nonvector_snapshot_vs_target": comparison(without_vectors(local), without_vectors(new_source)),
        "nonvector_source_vs_target": comparison(without_vectors(old_source), without_vectors(new_source)),
        "indexed_vector_checks": vector_checks, "vectors_retrieved_from_doc_values": restored_fields,
        "local_sha256": sha256_json(local),
        "source_sha256": sha256_json(old_source) if old_source is not None else None,
        "target_sha256": sha256_json(new_source) if new_source is not None else None,
        "target_reconstructed_sha256": sha256_json(reconstructed) if reconstructed is not None else None,
    }


def read_probe(client: ESHttp, indices: Sequence[str], query: Mapping[str, Any], target_to_source: Mapping[str, str]) -> Dict[str, Any]:
    try:
        body = client.json("POST", f"/{','.join(indices)}/_search", json={
            "size": TOP_K, "track_total_hits": True, "_source": False, "query": query,
        })
        if body.get("timed_out") or (body.get("_shards") or {}).get("failed", 0):
            return {"hits": [], "total": None, "error": {"type": "PartialSearchFailure", "timed_out": bool(body.get("timed_out")), "failed_shards": (body.get("_shards") or {}).get("failed", 0)}}
        hits = []
        for hit in response_hits(body):
            physical = str(hit.get("_index"))
            logical = target_to_source.get(physical, physical)
            hits.append({"index": logical, "_id": str(hit.get("_id")), "score": float(hit.get("_score") or 0.0)})
        return {"hits": hits, "total": total_hits(body), "error": None}
    except Exception as exc:
        # Error bodies can echo a query term or vector. Retain a fingerprint,
        # exception type and HTTP status without copying document contents.
        match = re.search(r"HTTP (\d+)", str(exc))
        return {"hits": [], "total": None, "error": {
            "type": type(exc).__name__, "http_status": int(match.group(1)) if match else None,
            "detail_sha256": sha256_json(str(exc)),
        }}


def paired_probe(source: ESHttp, target: ESHttp, source_indices: Sequence[str], target_indices: Sequence[str],
                 old_query: Optional[Mapping[str, Any]], new_query: Mapping[str, Any], *, vector: bool = False) -> Dict[str, Any]:
    names = dict(zip(target_indices, source_indices))
    old = read_probe(source, source_indices, old_query, {}) if old_query is not None else {"hits": [], "total": None, "error": {"type": "SourceVectorMappingUnavailable"}}
    new = read_probe(target, target_indices, new_query, names)
    old_keys = [(h["index"], h["_id"]) for h in old["hits"]]
    new_keys = [(h["index"], h["_id"]) for h in new["hits"]]
    overlap = set(old_keys) & set(new_keys)
    both_ok = old["error"] is None and new["error"] is None
    result = {
        "source_indices": list(source_indices), "target_indices": list(target_indices),
        "status": "ok" if both_ok else "error" if new["error"] or old_query is not None else "source_unavailable",
        "source": old, "target": new, "query_sha256": sha256_json(new_query),
        "transport_pass": both_ok,
        "result_set_equal": both_ok and set(old_keys) == set(new_keys),
        "result_order_equal": both_ok and old_keys == new_keys,
        "top1_same": bool(both_ok and old_keys and new_keys and old_keys[0] == new_keys[0]),
        "overlap": len(overlap), "recall_source_topk": round(len(overlap) / max(1, len(set(old_keys))), 4),
    }
    if vector:
        old_scores = {(h["index"], h["_id"]): h["score"] for h in old["hits"]}
        new_scores = {(h["index"], h["_id"]): h["score"] for h in new["hits"]}
        result.update({
            "comparison": "ES7 exact cosine+1 vs ES8 approximate HNSW (cosine+1)/2",
            "native_knn_pass": new["error"] is None and bool(new_keys),
            "normalized_score_max_diff_common_hits": max((abs(old_scores[k] - 2 * new_scores[k]) for k in overlap), default=None),
        })
    else:
        result["total_hits_equal"] = both_ok and old["total"] == new["total"]
        result["nonempty_result"] = bool(old_keys and new_keys)
    return result


def keyword_query(field: str, value: str, props: Mapping[str, Any]) -> Dict[str, Any]:
    exact = props.get(field, {}).get("type") in ("keyword", "constant_keyword")
    return {"term": {field: value}} if exact else {"match": {field: value}}


def source_vector_kind(props: Mapping[str, Any], field: str) -> Optional[str]:
    if vector_mapping(props, field).get("type") != "dense_vector":
        return None
    if "." in field and props.get(field.split(".", 1)[0], {}).get("type") == "nested":
        return "nested"
    return "root"


def choose_joint_states(states: Sequence[Mapping[str, Any]], shard_counts: Mapping[str, int]) -> List[Mapping[str, Any]]:
    ordered = sorted(states, key=lambda s: (int(s["docs_exported"]), str(s["source_index"])))
    one = next((s for s in ordered if shard_counts.get(str(s["source_index"])) == 1), None)
    three = next((s for s in ordered if shard_counts.get(str(s["source_index"])) == 3), None)
    return [one, three] if one and three else ordered[:2]


def target_vector_witness(target: ESHttp, states: Sequence[Mapping[str, Any]], field: str, kind: str,
                          shard_counts: Mapping[str, int]) -> Tuple[Optional[Dict[str, Any]], Optional[int], List[Dict[str, Any]]]:
    """Bound each new-target search below Alibaba's 48-shard query limit."""
    batches: List[List[Mapping[str, Any]]] = []
    pending: List[Mapping[str, Any]] = []
    primary_count = 0
    for state in states:
        count = shard_counts[str(state["source_index"])]
        if count > 40:
            raise ValueError("one index exceeds the safe vector-witness search shard budget")
        if pending and primary_count + count > 40:
            batches.append(pending)
            pending, primary_count = [], 0
        pending.append(state)
        primary_count += count
    if pending:
        batches.append(pending)
    witness = None
    total = 0
    errors = []
    for batch in batches:
        names = [str(s["target_index"]) for s in batch]
        existence_query: Dict[str, Any] = {"exists": {"field": field}}
        if kind == "nested":
            existence_query = {"nested": {"path": field.split(".", 1)[0], "query": existence_query}}
        try:
            body = target.json("POST", "/" + ",".join(names) + "/_search", json={
                "size": 1, "track_total_hits": True, "_source": [field], "query": existence_query,
            })
            if body.get("timed_out") or (body.get("_shards") or {}).get("failed", 0):
                raise RuntimeError("vector witness search returned partial results")
            total += total_hits(body)
            hit = next(iter(response_hits(body)), None)
            if witness is None and hit and first_vector(hit.get("_source") or {}, field) is not None:
                physical_to_source = {str(s["target_index"]): str(s["source_index"]) for s in batch}
                witness = {"_id": hit["_id"], "_source": hit["_source"], "__index": physical_to_source[str(hit["_index"])]}
        except Exception as exc:
            errors.append({"indices": [str(s["source_index"]) for s in batch],
                           "primary_shards": sum(shard_counts[str(s["source_index"])] for s in batch),
                           "type": type(exc).__name__, "detail_sha256": sha256_json(str(exc))})
    return witness, None if errors else total, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ES7 versus ES8 online migration verifier")
    parser.add_argument("--source-config", required=True, help="read-only ES7 endpoint JSON")
    parser.add_argument("--target-config", required=True, help="ES8 provider JSON")
    parser.add_argument("--dump-dir", required=True, help="local dump directory")
    parser.add_argument("--shard-plan", type=Path, help="restrict verification to the plan's selected indices")
    parser.add_argument("--sample-size", type=int, default=400, help="total docs across both providers (100-500)")
    parser.add_argument("--seed", default="es7-es8-online-20261002")
    parser.add_argument("--indices", nargs="*", default=[])
    parser.add_argument("--report", default="", help="JSON report path")
    parser.add_argument("--resume-report", action="store_true", help="reuse completed checks in --report and finish missing probes")
    args = parser.parse_args()
    if not 100 <= args.sample_size <= 500:
        parser.error("--sample-size must be between 100 and 500")
    dump_dir = Path(args.dump_dir)
    states = select_states(dump_dir, args.indices, args.shard_plan)
    if not states:
        raise SystemExit("没有已完成 import_done 的索引可抽查")
    by_provider: Dict[str, List[Dict[str, Any]]] = {"paas": [], "serverless": []}
    for state in states:
        by_provider[index_provider(str(state["source_index"]))].append(state)
    if not by_provider["paas"] or not by_provider["serverless"]:
        raise SystemExit("抽查范围必须同时覆盖 PaaS 和 Serverless")
    if args.sample_size < len(states):
        raise SystemExit("sample-size 必须足够每个选中索引至少抽查一条")
    quota_a = max(len(by_provider["paas"]), min(args.sample_size // 2, args.sample_size - len(by_provider["serverless"])))
    samples = {
        "paas": stratified_prefix_sample(by_provider["paas"], quota_a, args.seed + ":paas"),
        "serverless": stratified_prefix_sample(by_provider["serverless"], args.sample_size - quota_a, args.seed + ":serverless"),
    }
    source_cfg = extract_endpoint(load_json(Path(args.source_config)))
    targets_cfg = target_endpoints(load_json(Path(args.target_config)))
    source = ESHttp(source_cfg)
    targets = {name: ESHttp(cfg) for name, cfg in targets_cfg.items()}
    planned_shards = {}
    if args.shard_plan:
        planned_shards = {str(s["source_index"]): int(s["target_shards"]) for s in load_json(args.shard_plan)["selected"]}

    # Verify all targets before issuing any query to the old ES7 service.
    actual_shards: Dict[str, int] = {}
    for provider, provider_states in by_provider.items():
        names = [str(s["target_index"]) for s in provider_states]
        response = targets[provider].request("HEAD", "/" + ",".join(names))
        if response.status_code != 200:
            raise RuntimeError(f"target scope not fully present: {provider}, HTTP {response.status_code}")
        settings = targets[provider].json("GET", "/" + ",".join(names) + "/_settings", params={"flat_settings": "true"})
        for state in provider_states:
            index = str(state["source_index"])
            physical = str(state["target_index"])
            if physical not in settings:
                raise RuntimeError(f"target settings missing: {physical}")
            actual_shards[index] = int(settings[physical]["settings"]["index.number_of_shards"])
            if index in planned_shards and actual_shards[index] != planned_shards[index]:
                raise RuntimeError(f"target primary shard mismatch: {index}")

    output = Path(args.report) if args.report else dump_dir / "online_compare.json"
    report: Dict[str, Any] = {
        "run_at": utc_now(), "sample_size_requested": args.sample_size,
        "sample_size_actual": sum(len(x) for x in samples.values()), "seed": args.seed,
        "sampling_method": "deterministic prefix sample stratified by provider and index; not population-random",
        "read_only": True, "online_route_or_alias_changed": False,
        "selected_indices": sorted(str(s["source_index"]) for s in states),
        "selected_count": len(states), "all_selected_imports_done": True,
        "providers": {}, "summary": {},
    }
    if args.resume_report:
        previous = load_json(output)
        if (previous.get("selected_indices") != report["selected_indices"]
                or previous.get("seed") != args.seed
                or previous.get("sample_size_requested") != args.sample_size
                or previous.get("sample_size_actual") != report["sample_size_actual"]
                or previous.get("read_only") is not True):
            raise RuntimeError("resume report does not match the selected scope, sample size, seed or read-only mode")
        report = previous
        report["resumed_at"] = utc_now()
        report["resume_count"] = int(report.get("resume_count", 0)) + 1
        report["resume_reused_indices"] = []
        report.pop("finished_at", None)
        report["summary"] = {}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save_progress() -> None:
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(output)

    all_doc_results: List[Dict[str, Any]] = []
    for provider, provider_states in by_provider.items():
        target = targets[provider]
        sample_by_index: Dict[str, List[Dict[str, Any]]] = {}
        for record in samples[provider]:
            sample_by_index.setdefault(str(record["__index"]), []).append(record)
        provider_result: Dict[str, Any] = report["providers"].setdefault(provider, {
            "sample_docs": len(samples[provider]), "indices": {}, "keyword_probes": [],
            "knn_probes": [], "vector_coverage": {}, "joint_probes": [],
        })
        if provider_result.get("sample_docs") != len(samples[provider]):
            raise RuntimeError(f"resume provider sample quota changed: {provider}")
        source_props_by_index: Dict[str, Mapping[str, Any]] = {}

        def get_source_props(index: str) -> Mapping[str, Any]:
            if index not in source_props_by_index:
                source_props_by_index[index] = props_from_mapping(source.json("GET", f"/{index}/_mapping"), index)
            return source_props_by_index[index]

        state_by_index = {str(s["source_index"]): s for s in provider_states}
        for state in provider_states:
            source_index = str(state["source_index"])
            target_index = str(state["target_index"])
            records = sample_by_index[source_index]
            ids = [str(record["_id"]) for record in records]
            completed = provider_result["indices"].get(source_index)
            if completed is not None:
                if (completed.get("target_index") != target_index
                        or completed.get("expected_export_count") != int(state["docs_exported"])
                        or completed.get("sample_count") != len(records)
                        or {str(d["_id"]) for d in completed.get("doc_details", [])} != set(ids)):
                    raise RuntimeError(f"resume index checkpoint does not match current staging or sample: {source_index}")
                all_doc_results.extend(completed["doc_details"])
                report.setdefault("resume_reused_indices", []).append(source_index)
                if not any(q.get("index") == source_index for q in provider_result["keyword_probes"]):
                    probe_record = next((r for r in records if keyword_probe(r)), None)
                    if probe_record:
                        field, value = keyword_probe(probe_record)
                        query = keyword_query(field, value, get_source_props(source_index))
                        result = paired_probe(source, target, [source_index], [target_index], query, query)
                        result.update({"field": field, "query_type": next(iter(query)), "index": source_index})
                    else:
                        result = {"status": "skipped", "index": source_index, "reason": "no_keyword_in_sample"}
                    provider_result["keyword_probes"].append(result)
                save_progress()
                continue
            old_docs = mget(source, source_index, ids)
            new_docs = mget(target, target_index, ids)
            vector_ids = [str(r["_id"]) for r in records
                          if (new_docs.get(str(r["_id"])) or {}).get("_source") is not None
                          and any(field in r["_source"] and field not in new_docs[str(r["_id"])]["_source"]
                                  for field in ("title_embedding", "content_embedding"))]
            indexed_vectors: Dict[str, Dict[str, Any]] = {}
            vector_retrieval_error = None
            if vector_ids:
                try:
                    indexed_vectors = read_root_vector_values(target, target_index, vector_ids)
                except Exception as exc:
                    vector_retrieval_error = {"type": type(exc).__name__, "detail_sha256": sha256_json(str(exc))}
            doc_results = [compare_three_way(
                record, (old_docs.get(str(record["_id"])) or {}).get("_source"),
                (new_docs.get(str(record["_id"])) or {}).get("_source"),
                indexed_vectors.get(str(record["_id"])),
            ) for record in records]
            source_count = count_index(source, source_index)
            target_count = count_index(target, target_index)
            old_props = props_from_mapping(source.json("GET", f"/{source_index}/_mapping"), source_index)
            new_mapping = target.json("GET", f"/{target_index}/_mapping")
            new_props = props_from_mapping(new_mapping, target_index)
            source_props_by_index[source_index] = old_props
            provider_result["indices"][source_index] = {
                "provider": provider, "source_index": source_index, "target_index": target_index,
                "target_primary_shards": actual_shards[source_index], "sample_count": len(records),
                "source_count": source_count, "target_count": target_count,
                "count_equal": source_count == target_count,
                "expected_export_count": int(state["docs_exported"]),
                "target_count_matches_export": target_count == int(state["docs_exported"]),
                "source_count_matches_export": source_count == int(state["docs_exported"]),
                "source_del_flag": del_buckets(source, source_index),
                "target_del_flag": del_buckets(target, target_index),
                "mapping_vectors": vector_mapping_check(old_props, new_props),
                "target_source_excludes": (new_mapping.get(target_index, {}).get("mappings", {}).get("_source") or {}).get("excludes", []),
                "vector_doc_values_retrieval_error": vector_retrieval_error,
                "docs_snapshot_equal": sum(x["snapshot_vs_target"]["equal"] for x in doc_results),
                "docs_online_equal": sum(x["raw_source_vs_target"]["equal"] for x in doc_results),
                "docs_reconstructed_online_equal": sum(x["source_vs_target"]["equal"] for x in doc_results),
                "docs_compared": len(records), "doc_details": doc_results,
            }
            all_doc_results.extend(doc_results)
            probe_record = next((r for r in records if keyword_probe(r)), None)
            if probe_record:
                field, value = keyword_probe(probe_record)
                query = keyword_query(field, value, old_props)
                result = paired_probe(source, target, [source_index], [target_index], query, query)
                result.update({"field": field, "query_type": next(iter(query)), "index": source_index})
            else:
                result = {"status": "skipped", "index": source_index, "reason": "no_keyword_in_sample"}
            provider_result["keyword_probes"].append(result)
            save_progress()

        # Prefer witnesses in small indices to bound ES7 exact scan cost.
        vector_witnesses: Dict[str, Dict[str, Any]] = {}
        ordered_states = sorted(provider_states, key=lambda s: (int(s["docs_exported"]), str(s["source_index"])))
        for field, target_kind in VECTOR_FIELDS:
            if field in provider_result["vector_coverage"] and not provider_result["vector_coverage"][field].get("coverage_error"):
                continue
            witness = next((r for s in ordered_states for r in sample_by_index[str(s["source_index"])]
                            if first_vector(r["_source"], field) is not None), None)
            witness_origin = "local_sample"
            existing_total = None
            coverage_errors = []
            if witness is None:
                # A field missing from the 400 sampled docs is not proof that
                # the field has no vectors. Search only the new ES8 target for
                # an existing value before reporting a coverage gap.
                witness, existing_total, coverage_errors = target_vector_witness(target, provider_states, field, target_kind, actual_shards)
                if witness is not None:
                    witness_origin = "target_existing_vector"
            if witness is None:
                provider_result["vector_coverage"][field] = {
                    "native_knn_pass": False,
                    "reason": "witness_search_failed" if coverage_errors else "no_existing_vector" if existing_total == 0 else "existing_vector_not_retrievable_from_source",
                    "target_docs_with_vector": existing_total,
                    "coverage_error": coverage_errors,
                }
                save_progress()
                continue
            vector_witnesses[field] = witness
            source_index = str(witness["__index"])
            target_index = str(state_by_index[source_index]["target_index"])
            vector = first_vector(witness["_source"], field)
            old_kind = source_vector_kind(get_source_props(source_index), field)
            old_query = knn_query(field, old_kind, vector, native=False) if old_kind else None
            result = paired_probe(source, target, [source_index], [target_index], old_query,
                                  knn_query(field, target_kind, vector, native=True), vector=True)
            result.update({"field": field, "kind": target_kind, "source_kind": old_kind,
                           "query_vector_sha256": sha256_json(vector), "query_vector_dims": len(vector),
                           "witness_origin": witness_origin})
            provider_result["knn_probes"].append(result)
            provider_result["vector_coverage"][field] = {
                "native_knn_pass": result["native_knn_pass"], "source_comparable": old_kind is not None,
                "index": source_index, "target_docs_with_vector": existing_total,
            }
            save_progress()

        joint_states = choose_joint_states(provider_states, actual_shards)
        joint_indices = [str(s["source_index"]) for s in joint_states]
        joint_targets = [str(s["target_index"]) for s in joint_states]
        joint_records = [r for index in joint_indices for r in sample_by_index[index]]
        joint_shards = {index: actual_shards[index] for index in joint_indices}
        if not any(p.get("type") == "keyword" for p in provider_result["joint_probes"]):
            keyword_record = next((r for r in joint_records if keyword_probe(r)), None)
            if len(joint_indices) >= 2 and keyword_record:
                field, value = keyword_probe(keyword_record)
                query = keyword_query(field, value, get_source_props(str(keyword_record["__index"])))
                result = paired_probe(source, target, joint_indices, joint_targets, query, query)
                result.update({"type": "keyword", "field": field, "target_primary_shards": joint_shards})
            else:
                result = {"type": "keyword", "status": "skipped", "reason": "joint_keyword_witness_unavailable"}
            provider_result["joint_probes"].append(result)
            save_progress()
        # Root vectors avoid nested/object mapping differences across indices.
        if not any(p.get("type") == "vector" for p in provider_result["joint_probes"]):
            joint_vector = next(((field, kind, r) for field, kind in VECTOR_FIELDS
                                 for r in joint_records if first_vector(r["_source"], field) is not None), None)
            if len(joint_indices) >= 2 and joint_vector:
                field, target_kind, record = joint_vector
                vector = first_vector(record["_source"], field)
                kinds = {source_vector_kind(get_source_props(index), field) for index in joint_indices}
                old_kind = next(iter(kinds)) if len(kinds) == 1 else None
                old_query = knn_query(field, old_kind, vector, native=False) if old_kind else None
                result = paired_probe(source, target, joint_indices, joint_targets, old_query,
                                      knn_query(field, target_kind, vector, native=True), vector=True)
                result.update({"type": "vector", "field": field, "query_vector_sha256": sha256_json(vector),
                               "target_primary_shards": joint_shards})
            else:
                result = {"type": "vector", "status": "skipped", "reason": "joint_vector_witness_unavailable"}
            provider_result["joint_probes"].append(result)
        save_progress()

    index_checks = [item for provider in report["providers"].values() for item in provider["indices"].values()]
    keyword_checks = [item for provider in report["providers"].values() for item in provider["keyword_probes"] if item.get("status") != "skipped"]
    knn_checks = [item for provider in report["providers"].values() for item in provider["knn_probes"]]
    joint_checks = [item for provider in report["providers"].values() for item in provider["joint_probes"]]
    active_joint = [item for item in joint_checks if item.get("status") != "skipped"]
    coverage_gaps = [{"provider": provider, "field": field, **coverage}
                     for provider, values in report["providers"].items()
                     for field, coverage in values["vector_coverage"].items() if not coverage["native_knn_pass"]]
    classification_counts = dict(Counter(x["classification"] for x in all_doc_results))
    report["summary"] = {
        "sample_docs_compared": len(all_doc_results),
        "sample_docs_equal": sum(x["raw_source_vs_target"]["equal"] for x in all_doc_results),
        "sample_docs_reconstructed_equal": sum(x["source_vs_target"]["equal"] for x in all_doc_results),
        "sample_docs_snapshot_equal": sum(x["snapshot_vs_target"]["equal"] for x in all_doc_results),
        "sample_docs_raw_snapshot_equal": sum(x["raw_snapshot_vs_target"]["equal"] for x in all_doc_results),
        "sample_docs_nonvector_snapshot_equal": sum(x["nonvector_snapshot_vs_target"]["equal"] for x in all_doc_results),
        "sample_docs_with_vectors_filtered": sum(bool(x["vectors_retrieved_from_doc_values"]) for x in all_doc_results),
        "sample_vector_value_failures": sum(not v["equal"] for x in all_doc_results for v in x["indexed_vector_checks"].values()),
        "vector_doc_values_retrieval_errors": sum(bool(item["vector_doc_values_retrieval_error"]) for item in index_checks),
        "sample_docs_missing_source": sum(not x["source_found"] for x in all_doc_results),
        "sample_docs_missing_target": sum(not x["target_found"] for x in all_doc_results),
        "document_classifications": classification_counts,
        "indices_checked": len(index_checks), "selected_indices": len(states),
        "all_selected_indices_checked": len(index_checks) == len(states),
        "count_mismatch_indices": sum(not item["count_equal"] for item in index_checks),
        "export_count_mismatch_indices": sum(not item["target_count_matches_export"] for item in index_checks),
        "source_count_changed_indices": sum(not item["source_count_matches_export"] for item in index_checks),
        "del_flag_mismatch_indices": sum(item["source_del_flag"] != item["target_del_flag"] for item in index_checks),
        "vector_mapping_failures": sum(not mapping["target_hnsw_ok"] for item in index_checks for mapping in item["mapping_vectors"].values()),
        "keyword_probes": len(keyword_checks), "knn_probes": len(knn_checks), "joint_probes": len(active_joint),
        "keyword_errors": sum(item["status"] == "error" for item in keyword_checks),
        "knn_errors": sum(item["status"] == "error" for item in knn_checks),
        "keyword_result_mismatches": sum(not item["result_set_equal"] or not item["total_hits_equal"] for item in keyword_checks),
        "keyword_empty_results": sum(not item["nonempty_result"] for item in keyword_checks),
        "knn_result_set_mismatches": sum(not item["result_set_equal"] for item in knn_checks),
        "vector_coverage_complete": not coverage_gaps, "vector_coverage_gaps": coverage_gaps,
        "migration_snapshot_pass": bool(index_checks) and all(item["target_count_matches_export"] for item in index_checks)
                                   and all(x["snapshot_vs_target"]["equal"] for x in all_doc_results),
        "data_equal_pass": bool(index_checks) and all(item["count_equal"] and item["target_count_matches_export"]
                           and item["source_del_flag"] == item["target_del_flag"] for item in index_checks)
                           and all(x["raw_source_vs_target"]["equal"] for x in all_doc_results),
        "reconstructed_data_equal_pass": bool(index_checks) and all(item["count_equal"] and item["target_count_matches_export"]
                           and item["source_del_flag"] == item["target_del_flag"] for item in index_checks)
                           and all(x["source_vs_target"]["equal"] for x in all_doc_results),
        "vector_values_pass": bool(all_doc_results) and all(v["equal"] for x in all_doc_results for v in x["indexed_vector_checks"].values()),
        "vector_mapping_pass": bool(index_checks) and all(mapping["target_hnsw_ok"] for item in index_checks for mapping in item["mapping_vectors"].values()),
        "query_transport_pass": bool(keyword_checks and knn_checks) and all(item["transport_pass"] for item in keyword_checks + knn_checks + active_joint),
        "native_knn_pass_existing_fields": bool(knn_checks) and all(item["native_knn_pass"] for item in knn_checks),
        "joint_query_transport_pass": len(active_joint) == 2 * len(by_provider) and all(item["transport_pass"] for item in active_joint),
        "keyword_result_pass": bool(keyword_checks) and all(item["result_set_equal"] and item["total_hits_equal"] and item["nonempty_result"] for item in keyword_checks),
        "hnsw_result_note": "ANN top-k overlap and score differences are metrics; transport success does not prove identical results.",
    }
    report["finished_at"] = utc_now()
    save_progress()
    print(json.dumps({"report": str(output), "summary": report["summary"], "read_only": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
