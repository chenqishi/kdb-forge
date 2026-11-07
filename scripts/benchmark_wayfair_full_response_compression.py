#!/usr/bin/env python3
"""Isolate full-source ES retrieval and HTTP gzip cost, new endpoints only."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import logging
from pathlib import Path
import statistics
import sys
import time
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_wayfair_recall_stability import (INDICES, ROOTS, RoutedLegacyEngine,
    clean_rows, digest, load_inputs, now, old_comparison, read_json, readiness,
    validate_expected, write_json)
from audit_missing_indices_http import response_summary
from kdb.es.client_router import IndexClientRouter


def monitored_client(config, compress):
    private = copy.deepcopy(config)
    for provider in private["providers"].values():
        provider["http_compress"] = compress
        for key in ("client_options", "extra_params"):
            if key in provider:
                provider[key].pop("http_compress", None)
    router = IndexClientRouter(config=private)
    client = router.get_client_by_index("wayfair")
    metrics = []
    for node in client.transport.node_pool.all():
        original = node.perform_request
        def wrap(*args, _original=original, **kwargs):
            start = time.perf_counter()
            response = _original(*args, **kwargs)
            network_ms = (time.perf_counter() - start) * 1000
            hash_start = time.perf_counter()
            body_hash = hashlib.sha256(response.body).hexdigest()
            metrics.append({"network_plus_decompression_ms": network_ms,
                "diagnostic_hash_ms": (time.perf_counter() - hash_start) * 1000,
                "decoded_response_bytes": len(response.body), "decoded_response_sha256": body_hash,
                "content_length": response.meta.headers.get("content-length"),
                "content_encoding": response.meta.headers.get("content-encoding"),
                "http_status": response.meta.status})
            return response
        node.perform_request = wrap
    engine = RoutedLegacyEngine.__new__(RoutedLegacyEngine)
    engine.router = router
    engine.vector_fields = config["vector_fields"]
    engine.stable_query_preference = config.get("extra_params", {}).get("stable_query_preference", False)
    engine.retrieval_search_types = config.get("extra_params", {}).get("retrieval_search_types", {})
    return router, engine, client, metrics


def run_round(bundle, query, request, vector, old, full_source):
    from kdb.crud.service import KnowledgeService
    router, engine, client, metrics = bundle
    start_round = time.perf_counter()
    merged, stages = {}, []
    for index in INDICES:
        preference = engine._stable_search_preference(index, query)
        for route in ("bm25", "vector"):
            dsl = engine._build_search_query(query, include_text=route == "bm25",
                include_vector=route == "vector", vector_k=10, vector_boost=2.0 if route == "vector" else 1.0)
            kwargs = {"index": index, "query": dsl, "size": 10,
                      "ignore_unavailable": True, "allow_no_indices": True,
                      "preference": preference}
            search_type = engine.retrieval_search_types.get(index)
            if search_type:
                kwargs["search_type"] = search_type
            if full_source:
                kwargs["docvalue_fields"] = list(ROOTS)
            else:
                kwargs["source"] = False
            count_before = len(metrics)
            search_start = time.perf_counter()
            response = client.search(**kwargs)
            search_ms = (time.perf_counter() - search_start) * 1000
            wire = metrics[count_before:]
            if response.body.get("timed_out") or response.body.get("_shards", {}).get("failed"):
                raise RuntimeError("partial_ES_response")
            stage = {"index": index, "route": route, "search_type": search_type or "query_then_fetch",
                "preference_sha256": digest(preference), "http_search_calls": len(wire),
                "search_ms_without_diagnostic_hash": search_ms - sum(row["diagnostic_hash_ms"] for row in wire),
                "network_plus_decompression_ms": sum(row["network_plus_decompression_ms"] for row in wire),
                "json_deserialize_plus_client_overhead_ms": max(0, search_ms - sum(row["network_plus_decompression_ms"] + row["diagnostic_hash_ms"] for row in wire)),
                "http_responses": wire, "es_took_ms": response.body.get("took"), "_shards": response.body.get("_shards")}
            hydrate_start = time.perf_counter()
            body = engine._hydrate_vector_response(response, list(ROOTS) if full_source else [])
            stage["root_hydration_ms"] = (time.perf_counter() - hydrate_start) * 1000
            stage["candidate_id_order_sha256"] = digest([(hit["_index"], hit["_id"]) for hit in body["hits"]["hits"]])
            if full_source:
                merge_start = time.perf_counter()
                for hit in body["hits"]["hits"]:
                    key = (hit["_index"], hit["_id"])
                    if key not in merged:
                        merged[key] = {**hit.get("_source", {}), "_index": hit["_index"], "_id": hit["_id"]}
                    else:
                        for field, value in hit.get("_source", {}).items():
                            merged[key].setdefault(field, value)
                stage["candidate_merge_ms"] = (time.perf_counter() - merge_start) * 1000
            stages.append(stage)
    output = {"stages": stages,
        "decoded_response_bytes": sum(row["decoded_response_bytes"] for stage in stages for row in stage["http_responses"]),
        "network_plus_decompression_ms": sum(stage["network_plus_decompression_ms"] for stage in stages),
        "json_deserialize_plus_client_overhead_ms": sum(stage["json_deserialize_plus_client_overhead_ms"] for stage in stages),
        "root_hydration_ms": sum(stage["root_hydration_ms"] for stage in stages),
        "candidate_merge_ms": sum(stage.get("candidate_merge_ms", 0) for stage in stages)}
    lengths = [row["content_length"] for stage in stages for row in stage["http_responses"]]
    output["wire_content_length_bytes"] = sum(int(length) for length in lengths) if all(length and str(length).isdigit() for length in lengths) else None
    if full_source:
        rerank_start = time.perf_counter()
        calculator = KnowledgeService.__new__(KnowledgeService)
        results = []
        for (index, ident), doc in merged.items():
            score = calculator._cal_similarity(request["text"], vector, doc,
                search_type=request["search_type"], data_type=request.get("data_type", "text"),
                use_synonyms=request.get("use_synonyms", False))
            if score > request["score_threshold"]:
                results.append({"dataset": doc.get("dataset") or index, "id": ident, "score": float(score)})
        results.sort(key=lambda row: row["score"], reverse=True)
        output["results"] = results[:request["top_k"]]
        output["candidate_count"] = len(merged)
        output["rerank_sort_ms"] = (time.perf_counter() - rerank_start) * 1000
        output["old_comparison"] = old_comparison(output["results"], old)
        output["nested_vector_count_in_unique_candidates"] = sum(bool(entry.get("embedding")) for doc in merged.values() for entry in doc.get("indexes", []))
    output["round_ms_without_diagnostic_hash"] = (time.perf_counter() - start_round) * 1000 - sum(row["diagnostic_hash_ms"] for stage in stages for row in stage["http_responses"])
    return output


def run(args):
    request_cache = read_json(args.source_cache)
    request = request_cache["request"]
    if request["index_names"] != ",".join(INDICES) or request["search_type"] != "segment":
        raise RuntimeError("actual_segment_union_required")
    old = clean_rows(request_cache["runs"]["old"][0]["results"])
    runtime = read_json(args.search_config)
    config = read_json(Path(runtime["engine_config_path"]))
    if str(config.get("es_version")) != "8.17":
        raise RuntimeError("new_es817_required")
    fixed = read_json(args.private_vector)
    if fixed["request_sha256"] != digest(request):
        raise RuntimeError("fixed_query_vector_request_mismatch")
    names, _, _, _, identity = load_inputs(args)
    artifact = read_json(args.expected)
    validate_expected(artifact, names, identity)
    expected = {name: artifact["indices"][name]["counts"] for name in INDICES}
    _, ready = readiness(args, config["providers"]["serverless"], expected)
    if not ready:
        raise RuntimeError("union_restore_not_applied_complete")
    report = {"started_at": now(), "status": "prepared", "read_only": True, "old_requests": 0,
        "runtime_modified": False, "service_modified": False, "request_sha256": digest(request),
        "fixed_query_vector_sha256": digest(fixed["vector"]), "profile": False,
        "engine_config_path": runtime["engine_config_path"], "rounds": {"false": [], "true": []},
        "round_order": "Alternates False/True then True/False; first round includes connection warmup.",
        "timing_boundaries": {"network_plus_decompression": "HTTP node request, receive, gzip decode; excludes JSON deserialization.",
            "json_deserialize_plus_client_overhead": "search() wall minus HTTP-node time and diagnostic SHA hashing.",
            "root_hydration": "Recover two source-filtered vectors from fields, after JSON parsing.",
            "rerank": "Same production similarity formula, threshold and sorting; excludes embedding and HTTP API."}}
    write_json(args.report, report)
    if not args.execute:
        print(json.dumps({"status": "prepared", "network_requests": 0}))
        return 0
    from kdb.embedding.client import build_embedding_client
    embedding = build_embedding_client(runtime["embedding_config_path"])
    start = time.perf_counter()
    fresh = embedding.text2embedding(request["text"]).tolist()
    report["isolated_embedding"] = {"calls": 1, "elapsed_ms": (time.perf_counter() - start) * 1000,
        "dims": len(fresh), "sha256": digest(fresh), "same_as_fixed_vector": digest(fresh) == digest(fixed["vector"]),
        "used_for_raw_experiments": False}
    groups = copy.deepcopy(request["condition_dicts"])
    for group in groups:
        group.setdefault("audit_result", [1, 2, -1])
    query = {"query": request["text"], "attribute": groups, "vector": {"value": fixed["vector"]}}
    bundles = {compress: monitored_client(config, compress) for compress in (False, True)}
    try:
        report["status"] = "measuring"
        for repeat in range(args.repeats):
            for compress in (False, True) if repeat % 2 == 0 else (True, False):
                row = run_round(bundles[compress], query, request, fixed["vector"], old, True)
                row["round"] = repeat
                report["rounds"][str(compress).lower()].append(row)
                write_json(args.report, report)
                print(json.dumps({"compression": compress, "round": repeat,
                    "elapsed_ms": row["round_ms_without_diagnostic_hash"], "decoded_bytes": row["decoded_response_bytes"],
                    "wire_content_length": row["wire_content_length_bytes"], "old_order_same": row["old_comparison"]["same_order"]}), flush=True)
        report["source_false_control"] = {str(compress).lower(): run_round(bundles[compress], query, request, fixed["vector"], old, False)
                                          for compress in (False, True)}
    finally:
        for router, _, _, _ in bundles.values():
            router.close()
    report["isolated_api"] = response_summary("http://127.0.0.1:8012/search", request, None, 60)
    report["isolated_api"]["old_comparison"] = old_comparison(report["isolated_api"].get("results", []), old)
    report["summary"] = {}
    for compress, rows in report["rounds"].items():
        keys = ("round_ms_without_diagnostic_hash", "network_plus_decompression_ms", "json_deserialize_plus_client_overhead_ms", "root_hydration_ms", "candidate_merge_ms", "rerank_sort_ms", "decoded_response_bytes")
        report["summary"][compress] = {"rounds": len(rows), **{f"median_{key}": statistics.median(row[key] for row in rows) for key in keys},
            "min_round_ms": min(row["round_ms_without_diagnostic_hash"] for row in rows),
            "max_round_ms": max(row["round_ms_without_diagnostic_hash"] for row in rows),
            "all_old_ids_and_order_same": all(row["old_comparison"]["same_order"] for row in rows),
            "common_max_score_diff": max(row["old_comparison"]["common_max_score_diff"] for row in rows),
            "all_content_encodings": sorted({str(m["content_encoding"]) for row in rows for stage in row["stages"] for m in stage["http_responses"]}),
            "all_wire_lengths_available": all(row["wire_content_length_bytes"] is not None for row in rows)}
    report.update(status="complete", finished_at=now(),
        full_response_new_es_searches=args.repeats * 8, source_false_new_es_searches=8, new_api_calls=1,
        median_compressed_to_uncompressed_ratio=report["summary"]["true"]["median_round_ms_without_diagnostic_hash"] / report["summary"]["false"]["median_round_ms_without_diagnostic_hash"])
    write_json(args.report, report)
    print(json.dumps({"status": "complete", "summary": report["summary"],
        "embedding": report["isolated_embedding"], "isolated_api_elapsed_seconds": report["isolated_api"].get("elapsed_seconds"),
        "median_compressed_to_uncompressed_ratio": report["median_compressed_to_uncompressed_ratio"]}), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--source-cache", type=Path, default=Path("/tmp/sg_wayfair_segment_repeat_20261004.json"))
    p.add_argument("--search-config", type=Path, default=Path("config/config_search_runtime.local.json"))
    p.add_argument("--private-vector", type=Path, default=Path("/tmp/kdb_wayfair_segment_fixed_query_vector_20261004.json"))
    p.add_argument("--expected", type=Path, default=Path("artifacts/all81_expected_root_counts_20261004.json"))
    p.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    p.add_argument("--priority-state", type=Path, default=Path("artifacts/root_restore_priority_wayfair_joint_20261004.json"))
    p.add_argument("--shard-plan", default="migration_runs/local_dump_20261001/data/shard_plan_1g.json")
    p.add_argument("--dump-dir", default="migration_runs/local_dump_20261001/data")
    p.add_argument("--incremental-manifest", default="migration_runs/incremental_local_20261002T161500Z/manifest.json")
    p.add_argument("--incremental-report", default="migration_runs/incremental_local_20261002T161500Z/import_report.json")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args(); args.indices = None
    warnings.filterwarnings("ignore"); logging.disable(logging.CRITICAL)
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
