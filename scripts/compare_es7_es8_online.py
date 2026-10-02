#!/usr/bin/env python3
"""Read-only online verification of an ES7 dump against ES8 staging indices.

The script is intentionally a verifier only.  It does not create/delete indices,
refresh, update aliases, or write documents.  It uses the local gzip dump to pick
a deterministic sample, then reads the same ids from the old ES7 source and the
new ES8 physical index.  It also checks counts, mappings, del_flag buckets,
keyword result overlap, and one native-vector/script-score pair per vector field
for each provider that has that vector.

Typical use (after every local import checkpoint is ``import_done``)::

    python scripts/compare_es7_es8_online.py \\
      --source-config /path/to/es7-readonly.json \\
      --target-config config/config_es_runtime.local.json \\
      --dump-dir migration_runs/local_dump_20261001/data \\
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


def chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def mget(client: ESHttp, index: str, ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for part in chunks(list(ids), MAX_MGET):
        body = client.json("POST", f"/{index}/_mget", json={"docs": [{"_id": str(x)} for x in part]})
        for doc in body.get("docs", []) or []:
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
        )
        result[field] = {
            "source_type": old.get("type"),
            "source_dims": old.get("dims"),
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


def select_states(dump_dir: Path, requested: Sequence[str]) -> List[Dict[str, Any]]:
    manifest = load_json(dump_dir / "manifest.json")
    selected = {str(item.get("source_index")) for item in manifest.get("indices", []) if item.get("source_index")}
    if requested:
        selected &= set(requested)
    states: List[Dict[str, Any]] = []
    for path in sorted((dump_dir / "states").glob("*.json")):
        state = load_json(path)
        if state.get("source_index") not in selected:
            continue
        # Never compare an index that was not fully imported.  This prevents a
        # partial staging index from being mistaken for a successful migration.
        if state.get("import_status") != "done" or state.get("status") != "import_done":
            continue
        states.append(state)
    return states


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ES7 versus ES8 online migration verifier")
    parser.add_argument("--source-config", required=True, help="read-only ES7 endpoint JSON")
    parser.add_argument("--target-config", required=True, help="ES8 provider JSON")
    parser.add_argument("--dump-dir", required=True, help="local dump data directory containing manifest.json and states/")
    parser.add_argument("--sample-size", type=int, default=400, help="total docs sampled across both providers (100-500)")
    parser.add_argument("--seed", default="es7-es8-online-20261002")
    parser.add_argument("--indices", nargs="*", default=[])
    parser.add_argument("--report", default="", help="JSON report path; defaults to <dump-dir>/online_compare.json")
    args = parser.parse_args()
    if not 100 <= args.sample_size <= 500:
        parser.error("--sample-size must be between 100 and 500")
    dump_dir = Path(args.dump_dir)
    states = select_states(dump_dir, args.indices)
    if not states:
        raise SystemExit("没有已完成 import_done 的索引可抽查；先完成 ES8 导入")
    by_provider: Dict[str, List[Dict[str, Any]]] = {"paas": [], "serverless": []}
    for state in states:
        by_provider[index_provider(str(state["source_index"]))].append(state)
    if not by_provider["paas"] or not by_provider["serverless"]:
        raise SystemExit(f"抽查范围必须同时覆盖 PaaS 和 Serverless；当前完成状态为 paas={len(by_provider['paas'])}, serverless={len(by_provider['serverless'])}")

    # Split quota evenly, then give unused quota to the provider with fewer docs.
    quota_a = args.sample_size // 2
    quota_b = args.sample_size - quota_a
    samples = {
        "paas": deterministic_sample(by_provider["paas"], quota_a, args.seed + ":paas"),
        "serverless": deterministic_sample(by_provider["serverless"], quota_b, args.seed + ":serverless"),
    }
    if not samples["paas"] or not samples["serverless"]:
        raise SystemExit("PaaS/Serverless 中至少有一侧没有可抽取文档")

    source_cfg = extract_endpoint(load_json(Path(args.source_config)))
    targets_cfg = target_endpoints(load_json(Path(args.target_config)))
    source = ESHttp(source_cfg)
    targets = {name: ESHttp(cfg) for name, cfg in targets_cfg.items()}
    report: Dict[str, Any] = {
        "run_at": utc_now(),
        "sample_size_requested": args.sample_size,
        "sample_size_actual": sum(len(x) for x in samples.values()),
        "seed": args.seed,
        "read_only": True,
        "online_route_or_alias_changed": False,
        "providers": {},
        "summary": {},
    }

    all_doc_results: List[Dict[str, Any]] = []
    for provider, provider_states in by_provider.items():
        target = targets[provider]
        sample_by_index: Dict[str, List[Dict[str, Any]]] = {}
        for record in samples[provider]:
            sample_by_index.setdefault(str(record["__index"]), []).append(record)
        provider_result: Dict[str, Any] = {"sample_docs": len(samples[provider]), "indices": {}, "keyword_probes": [], "knn_probes": []}
        for state in provider_states:
            source_index = str(state["source_index"])
            target_index = str(state.get("target_index") or staged_name(source_index, str(load_json(dump_dir / "import_manifest.json").get("run_id", "local_dump_20261001"))))
            # Only query online for indices contributing to the sample, while
            # still recording all completed counts/mapping checks if requested.
            records = sample_by_index.get(source_index, [])
            if not records:
                continue
            ids = [str(record["_id"]) for record in records]
            old_docs = mget(source, source_index, ids)
            new_docs = mget(target, target_index, ids)
            doc_results = []
            equal_count = 0
            for record in records:
                doc_id = str(record["_id"])
                old_source = (old_docs.get(doc_id) or {}).get("_source")
                new_source = (new_docs.get(doc_id) or {}).get("_source")
                mismatch_paths: List[str] = []
                same = bool(old_source is not None and new_source is not None)
                max_diff = 0.0
                if same:
                    same, max_diff = compare_values(old_source, new_source, mismatches=mismatch_paths)
                if same:
                    equal_count += 1
                doc_results.append({"_id": doc_id, "source_found": old_source is not None, "target_found": new_source is not None, "equal": same, "max_numeric_diff": max_diff, "mismatch_paths": mismatch_paths[:10], "source_sha256": sha256_json(old_source) if old_source is not None else None, "target_sha256": sha256_json(new_source) if new_source is not None else None})
            source_count = count_index(source, source_index)
            target_count = count_index(target, target_index)
            old_mapping = source.json("GET", f"/{source_index}/_mapping")
            new_mapping = target.json("GET", f"/{target_index}/_mapping")
            old_props = props_from_mapping(old_mapping, source_index)
            new_props = props_from_mapping(new_mapping, target_index)
            index_result = {
                "provider": provider,
                "source_index": source_index,
                "target_index": target_index,
                "sample_count": len(records),
                "source_count": source_count,
                "target_count": target_count,
                "count_equal": source_count == target_count,
                "expected_export_count": state.get("docs_exported"),
                "target_count_matches_export": target_count == int(state.get("docs_exported", -1)),
                "source_del_flag": del_buckets(source, source_index),
                "target_del_flag": del_buckets(target, target_index),
                "mapping_vectors": vector_mapping_check(old_props, new_props),
                "docs_equal": equal_count,
                "docs_compared": len(records),
                "docs_missing_source": sum(1 for x in doc_results if not x["source_found"]),
                "docs_missing_target": sum(1 for x in doc_results if not x["target_found"]),
                "doc_details": doc_results,
            }
            provider_result["indices"][source_index] = index_result
            provider_result["keyword_probes"].append(run_keyword_probe(source, target, source_index, target_index, records[0]))
            vector_records = records
            for field, kind in VECTOR_FIELDS:
                vector_record = next((r for r in vector_records if first_vector(r.get("_source") or {}, field) is not None), None)
                if vector_record:
                    provider_result["knn_probes"].append(run_knn_probe(source, target, source_index, target_index, vector_record, field, kind))
            all_doc_results.extend(doc_results)
        report["providers"][provider] = provider_result

    # Summary deliberately contains aggregates only; detailed document hashes
    # and mismatch paths are retained in the report for review without source text.
    report["summary"] = {
        "sample_docs_compared": len(all_doc_results),
        "sample_docs_equal": sum(1 for x in all_doc_results if x.get("equal")),
        "sample_docs_missing_source": sum(1 for x in all_doc_results if not x.get("source_found")),
        "sample_docs_missing_target": sum(1 for x in all_doc_results if not x.get("target_found")),
        "indices_checked": sum(len(x["indices"]) for x in report["providers"].values()),
        "keyword_probes": sum(len(x["keyword_probes"]) for x in report["providers"].values()),
        "knn_probes": sum(len(x["knn_probes"]) for x in report["providers"].values()),
    }
    output = Path(args.report) if args.report else dump_dir / "online_compare.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "summary": report["summary"], "read_only": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
