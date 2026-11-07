#!/usr/bin/env python3
"""Diagnose new ES recall with one fixed production query embedding.

Read-only: default prepares a local plan; --execute sends only new ES requests.
Reports contain IDs, hashes, scores and counts, never source text or vectors.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import math
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audit_key3_restored_data import AuditFailure, NewTarget, digest
from audit_wayfair_joint_restored import readiness
from audit_all81_restored_counts import validate_expected
from compare_legacy_search_http import logical_dataset, now, read_json, write_json
from restore_local_root_vectors import load_inputs
from kdb.es.engine import RoutedLegacyEngine

INDICES = ("wayfair", "wayfair_wayfair_test2")
ROOTS = ("title_embedding", "content_embedding")


def identities(rows):
    return [(row["dataset"], row["id"]) for row in rows]


def old_comparison(rows, old):
    a, b = identities(old), identities(rows)
    aa, bb = {(x["dataset"], x["id"]): x for x in old}, {(x["dataset"], x["id"]): x for x in rows}
    common = aa.keys() & bb.keys()
    return {"common": len(common), "count": len(rows), "same_order": a == b,
            "same_set": set(a) == set(b), "top2_same": a[:2] == b[:2],
            "common_max_score_diff": max((abs(aa[k]["score"] - bb[k]["score"]) for k in common), default=None),
            "old_only_ids": [list(x) for x in sorted(set(a) - set(b))],
            "new_only_ids": [list(x) for x in sorted(set(b) - set(a))]}


def clean_rows(rows):
    return [{"id": str(row["id"]), "dataset": logical_dataset(row.get("dataset")),
             "score": float(row["score"])} for row in rows]


def profile_shards(body):
    output = []
    for row in (body.get("profile") or {}).get("shards", []):
        groups = re.findall(r"\[([^\]]+)\]", str(row.get("id", "")))
        output.append({"node_sha256": digest(groups[0] if groups else row.get("id")),
                       "index": groups[-2].split(":")[-1] if len(groups) >= 3 else None,
                       "shard": groups[-1] if len(groups) >= 3 else None,
                       "query_types": sorted({q.get("type") for search in row.get("searches", [])
                                               for q in search.get("query", []) if q.get("type")})})
    return sorted(output, key=lambda row: (str(row["index"]), str(row["shard"]), row["node_sha256"]))


def index_stats(target):
    try:
        body = target.call("GET", "/" + ",".join(INDICES) + "/_stats/docs,segments,merge,refresh,indexing",
                           params={"level": "shards"})
        output = {}
        for name, data in body["indices"].items():
            shards = []
            for shard, copies in data.get("shards", {}).items():
                for row in copies:
                    routing = row.get("routing", {})
                    shards.append({"shard": shard, "primary": routing.get("primary"),
                                   "node_sha256": digest(routing.get("node")),
                                   "docs": row.get("docs"), "segments_count": (row.get("segments") or {}).get("count"),
                                   "merges": row.get("merges"), "refresh_total": (row.get("refresh") or {}).get("total"),
                                   "index_total": (row.get("indexing") or {}).get("index_total")})
            output[name] = {"uuid_sha256": digest(data.get("uuid")), "shards": shards}
        return {"status": "complete", "indices": output}
    except Exception as exc:
        return {"status": "unavailable", "error_type": type(exc).__name__}


def copy_choices(target):
    body = target.call("GET", "/wayfair/_stats/docs", params={"level": "shards"})
    copies = body["indices"]["wayfair"]["shards"]
    output, evidence = [], {}
    for primary in (True, False):
        label = "primary_only" if primary else "replica_only"
        nodes = [str(row["routing"]["node"]) for rows in copies.values() for row in rows
                 if row["routing"]["primary"] is primary]
        if len(nodes) != 3 or len(set(nodes)) != 3:
            raise RuntimeError("copy_isolation_needs_one_unique_node_per_wayfair_shard_copy")
        preference = "_only_nodes:" + ",".join(nodes)
        try:
            selection = target.call("GET", "/wayfair/_search_shards", params={"preference": preference})
            selected = [{"shard": row["shard"], "primary": row["primary"], "node_sha256": digest(row.get("node"))}
                        for group in selection["shards"] for row in group]
            verified = len(selected) == 3 and all(row["primary"] is primary for row in selected)
            evidence[label] = {"selection_verified": verified, "shards": selected}
            if not verified:
                raise RuntimeError("search_shards_did_not_confirm_forced_copy_selection")
        except AuditFailure as exc:
            evidence[label] = {"selection_verified": False, "error_code": str(exc),
                               "requested_node_sha256": [digest(node) for node in nodes]}
        output.append((label, preference))
    return output, evidence


def stage_summary(runs):
    done = [row for row in runs if row.get("status") == "complete"]
    return {"runs": len(runs), "successful": len(done), "failures": len(runs) - len(done),
            "unique_id_orders": len({digest(identities(row["hits"])) for row in done}),
            "unique_score_sequences": len({digest(row["hits"]) for row in done}),
            "unique_shard_node_selections": len({digest(row["profile_shards"]) for row in done}),
            "unique_exact_totals": len({digest(row["total"]) for row in done})}


def fetch_documents(target, keys):
    docs = {}
    for name in INDICES:
        ids = sorted({ident for index, ident in keys if index == name})
        for start in range(0, len(ids), 32):
            batch = ids[start:start + 32]
            source, vectors = target.read(name, batch)
            for ident in batch:
                if not source.get(ident, {}).get("found"):
                    raise RuntimeError("candidate_source_missing")
                doc = copy.deepcopy(source[ident]["_source"])
                for field in ROOTS:
                    if field not in doc and vectors.get(ident, {}).get(field) is not None:
                        doc[field] = vectors[ident][field]
                doc.update(_id=ident, _index=name)
                docs[(name, ident)] = doc
    return docs


def rerank(round_routes, documents, request, vector):
    from kdb.crud.service import KnowledgeService
    calculator = KnowledgeService.__new__(KnowledgeService)
    merged = {}
    for index in INDICES:
        for route in ("bm25", "vector"):
            row = round_routes[(index, route)]
            if row.get("status") != "complete":
                return {"status": "incomplete_raw_stage"}
            for hit in row["hits"]:
                key = (hit["index"], hit["id"])
                merged.setdefault(key, documents[key])
    results = []
    for (name, ident), doc in merged.items():
        score = calculator._cal_similarity(request["text"], vector, doc,
            search_type=request["search_type"], data_type=request.get("data_type", "text"),
            use_synonyms=request.get("use_synonyms", False))
        if score > request["score_threshold"]:
            results.append({"dataset": logical_dataset(doc.get("dataset") or name), "id": ident, "score": float(score)})
    results.sort(key=lambda row: row["score"], reverse=True)
    return {"status": "complete", "candidate_count": len(merged), "results": results[:request["top_k"]]}


def run(args):
    cache = read_json(args.source_cache)
    request = cache["request"]
    if request.get("index_names") != ",".join(INDICES) or request.get("search_type") != "segment" or request.get("top_k") != 10:
        raise RuntimeError("actual_segment_union_request_required")
    old_runs = cache["runs"]["old"]
    if not old_runs or any(row.get("status") != 200 for row in old_runs):
        raise RuntimeError("stable_old_cache_required")
    old = clean_rows(old_runs[0]["results"])
    if len({digest(clean_rows(row["results"])) for row in old_runs}) != 1:
        raise RuntimeError("old_cache_not_stable")
    search_config = read_json(args.search_config)
    engine_config = read_json(Path(search_config["engine_config_path"]))
    if str(engine_config.get("es_version")) != "8.17":
        raise RuntimeError("new_es817_required")
    endpoint = engine_config["providers"]["serverless"]
    expected_artifact = read_json(args.expected)
    names, _, _, _, identity = load_inputs(args)
    validate_expected(expected_artifact, names, identity)
    expected = {name: expected_artifact["indices"][name]["counts"] for name in INDICES}
    report = {"started_at": now(), "status": "prepared", "read_only": True, "reads_old_es": False,
              "calls_old_http": False, "calls_new_http": False, "request_sha256": digest(request),
              "query_sha256": hashlib.sha256(request["text"].encode()).hexdigest(),
              "old_cache_runs": len(old_runs), "old_cache_stable": True, "cached_old_results": old,
              "cached_new_unique_id_orders": len({digest(identities(clean_rows(row["results"]))) for row in cache["runs"]["new"]}),
              "conditions_augmented_like_service": True,
              "route_budget_each_index": request["top_k"], "vector_k": 10, "num_candidates": 100,
              "single_vector_boost": 2.0, "repeats": args.repeats, "stages": {}, "reconstructed_rounds": {},
              "profiling_enabled_all_searches": True,
              "latency_note": "Diagnostic profile overhead and cache warmup prevent production latency conclusions."}
    write_json(args.report, report)
    if not args.execute:
        print(json.dumps({"status": "prepared", "network_requests": 0, "request_sha256": digest(request)}))
        return 0
    _, ready = readiness(args, endpoint, expected)
    if not ready:
        raise RuntimeError("wayfair_and_test2_applied_restore_not_complete")
    report.update(status="running", restore_gate_pass=True)
    vector_file = args.private_vector
    if vector_file.exists():
        saved = read_json(vector_file)
        if saved.get("request_sha256") != digest(request) or saved.get("embedding_config_sha256") != digest(read_json(Path(search_config["embedding_config_path"]))):
            raise RuntimeError("saved_fixed_vector_inputs_changed")
        vector = saved["vector"]
        generated = False
    else:
        from kdb.embedding.client import build_embedding_client
        embedding = build_embedding_client(search_config["embedding_config_path"])
        vector = embedding.text2embedding(request["text"]).tolist()
        write_json(vector_file, {"request_sha256": digest(request), "vector": vector,
                   "embedding_config_sha256": digest(read_json(Path(search_config["embedding_config_path"])))}, private=True)
        generated = True
    if len(vector) != 1024 or not all(math.isfinite(float(v)) for v in vector):
        raise RuntimeError("invalid_fixed_query_vector")
    report.update(query_embedding_generated_this_run=generated, query_embedding_calls_this_run=int(generated),
                  fixed_query_vector_sha256=digest(vector), fixed_query_vector_dims=len(vector),
                  fixed_vector_private_file=str(vector_file))
    engine = RoutedLegacyEngine.__new__(RoutedLegacyEngine)
    engine.vector_fields = {"indexes.embedding": 1024}
    groups = copy.deepcopy(request["condition_dicts"])
    for group in groups:
        group.setdefault("audit_result", [1, 2, -1])
    query = {"query": request["text"], "attribute": groups, "vector": {"value": vector}}
    dsls = {route: engine._build_search_query(query, include_text=route == "bm25", include_vector=route == "vector",
                                            vector_k=10, vector_boost=2.0 if route == "vector" else 1.0)
            for route in ("bm25", "vector")}
    if args.copy_isolation:
        dsls["vector_no_filter_score"] = copy.deepcopy(dsls["vector"])
        outer_bool = dsls["vector_no_filter_score"]["bool"]
        outer_bool["filter"] = outer_bool.pop("must")
    report["query_dsl_sha256"] = {route: digest(dsl) for route, dsl in dsls.items()}
    target = NewTarget(endpoint)
    report["stats_before"] = index_stats(target)
    choices = [("default", None), ("fixed", args.preference)]
    if args.copy_isolation:
        choices, report["forced_copy_selection"] = copy_choices(target)
        report["vector_no_filter_score_note"] = "Diagnostic only: same native KNN/filter/k/nc/boost with outer bool.must moved to filter. Production DSL unchanged."
    report["profile_node_identity_verified"] = False
    report["profile_node_identity_note"] = "Platform profile node hash does not match physical _stats routing nodes; use _search_shards forced-copy evidence for replica attribution."
    write_json(args.report, report)
    all_rounds = {}
    for search_type in ("query_then_fetch", "dfs_query_then_fetch"):
        for choice, preference in choices:
            experiment = f"{search_type}:{choice}"
            all_rounds[experiment] = []
            for repeat in range(args.repeats):
                round_routes = {}
                for index in INDICES:
                    for route in dsls:
                        if route == "vector_no_filter_score" and index != "wayfair":
                            continue
                        stage_key = f"{experiment}:{index}:{route}"
                        params = {"search_type": search_type, "ignore_unavailable": "true", "allow_no_indices": "true"}
                        if preference:
                            params["preference"] = preference
                        started = time.monotonic()
                        try:
                            body = target.call("POST", f"/{index}/_search", params=params,
                                json={"query": dsls[route], "size": 10, "_source": False, "profile": True})
                            hits = [{"index": str(hit["_index"]), "dataset": str(hit["_index"]),
                                     "id": str(hit["_id"]), "score": float(hit["_score"])}
                                    for hit in body["hits"]["hits"]]
                            row = {"status": "complete", "repeat": repeat, "hits": hits,
                                   "total": body["hits"]["total"], "_shards": body.get("_shards"),
                                   "profile_shards": profile_shards(body), "took_ms": body.get("took"),
                                   "elapsed_seconds": round(time.monotonic() - started, 4)}
                        except Exception as exc:
                            row = {"status": "failed", "repeat": repeat, "error_type": type(exc).__name__,
                                   "elapsed_seconds": round(time.monotonic() - started, 4)}
                            if isinstance(exc, AuditFailure):
                                row["error_code"] = str(exc)
                        round_routes[(index, route)] = row
                        report["stages"].setdefault(stage_key, {"runs": []})["runs"].append(row)
                        write_json(args.report, report)
                all_rounds[experiment].append(round_routes)
            print(json.dumps({"completed_experiment": experiment}), flush=True)
    report["stats_after"] = index_stats(target)
    for entry in report["stages"].values():
        entry["summary"] = stage_summary(entry["runs"])
    keys = {(hit["index"], hit["id"]) for entry in report["stages"].values()
            for row in entry["runs"] for hit in row.get("hits", [])}
    documents = fetch_documents(target, keys)
    report["candidate_documents"] = {f"{index}/{ident}": {"non_root_source_sha256": digest({k:v for k,v in doc.items() if k not in ROOTS}),
                      "title_sha256": digest(doc.get("title")), "content_sha256": digest(doc.get("content")),
                      "root_vector_sha256": {field: digest(doc.get(field)) for field in ROOTS}}
                      for (index,ident),doc in documents.items()}
    for experiment, rounds in all_rounds.items():
        outputs = []
        for round_routes in rounds:
            output = rerank(round_routes, documents, request, vector)
            if output["status"] == "complete":
                output["old_comparison"] = old_comparison(output["results"], old)
            outputs.append(output)
        done = [row for row in outputs if row["status"] == "complete"]
        report["reconstructed_rounds"][experiment] = {"runs": outputs,
            "summary": {"successful": len(done), "unique_id_orders": len({digest(identities(row["results"])) for row in done}),
                        "unique_score_sequences": len({digest(row["results"]) for row in done}),
                        "old_overlap_range": [min((row["old_comparison"]["common"] for row in done), default=None),
                                              max((row["old_comparison"]["common"] for row in done), default=None)],
                        "all_old_order_same": bool(done) and all(row["old_comparison"]["same_order"] for row in done)}}
    report.update(status="complete", finished_at=now())
    write_json(args.report, report)
    print(json.dumps({"status": "complete", "stage_summary": {k:v["summary"] for k,v in report["stages"].items()},
                      "reconstructed_summary": {k:v["summary"] for k,v in report["reconstructed_rounds"].items()}}), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-cache", type=Path, default=Path("/tmp/sg_wayfair_segment_repeat_20261004.json"))
    parser.add_argument("--search-config", type=Path, default=Path("config/config_search_runtime.local.json"))
    parser.add_argument("--private-vector", type=Path, default=Path("/tmp/kdb_wayfair_segment_fixed_query_vector_20261004.json"))
    parser.add_argument("--expected", type=Path, default=Path("artifacts/all81_expected_root_counts_20261004.json"))
    parser.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    parser.add_argument("--priority-state", type=Path, default=Path("artifacts/root_restore_priority_wayfair_joint_20261004.json"))
    parser.add_argument("--shard-plan", default="migration_runs/local_dump_20261001/data/shard_plan_1g.json")
    parser.add_argument("--dump-dir", default="migration_runs/local_dump_20261001/data")
    parser.add_argument("--incremental-manifest", default="migration_runs/incremental_local_20261002T161500Z/manifest.json")
    parser.add_argument("--incremental-report", default="migration_runs/incremental_local_20261002T161500Z/import_report.json")
    parser.add_argument("--preference", default="kdb-wayfair-fixed-stability-20261004")
    parser.add_argument("--copy-isolation", action="store_true")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.indices = None
    logging.disable(logging.CRITICAL)
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
