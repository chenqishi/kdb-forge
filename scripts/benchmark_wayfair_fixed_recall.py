#!/usr/bin/env python3
"""Measure candidate-stage DFS overhead with fixed query/pref, no profile.

Read-only new ES only. Source is disabled to isolate retrieval coordination;
these timings exclude embedding, source hydration, reranking and API overhead.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_wayfair_recall_stability import (INDICES, NewTarget, RoutedLegacyEngine,
    digest, load_inputs, now, read_json, readiness, validate_expected, write_json)


def run(args):
    request = read_json(args.source_cache)["request"]
    runtime = read_json(args.search_config)
    config = read_json(Path(runtime["engine_config_path"]))
    if str(config.get("es_version")) != "8.17" or request["index_names"] != ",".join(INDICES):
        raise RuntimeError("new_es817_actual_union_required")
    endpoint = config["providers"]["serverless"]
    fixed = read_json(args.private_vector)
    if fixed["request_sha256"] != digest(request):
        raise RuntimeError("fixed_vector_request_mismatch")
    artifact = read_json(args.expected)
    names, _, _, _, identity = load_inputs(args)
    validate_expected(artifact, names, identity)
    expected = {name: artifact["indices"][name]["counts"] for name in INDICES}
    _, ready = readiness(args, endpoint, expected)
    if not ready:
        raise RuntimeError("union_restore_gate_not_ready")
    report = {"started_at": now(), "read_only": True, "old_requests": 0, "profile": False,
        "request_sha256": digest(request), "fixed_vector_sha256": digest(fixed["vector"]),
        "embedding_calls": 0, "source": False, "custom_preference": args.preference,
        "excluded_timing_stages": ["embedding", "source_hydration", "local_rerank", "HTTP_API"],
        "measurement": "Serial four ES candidate searches only; source=false isolates extra DFS coordination overhead.",
        "round_order": "QTF/DFS order alternates each round, after one warmup per mode.",
        "status": "prepared", "rounds": {"query_then_fetch": [], "dfs_query_then_fetch": []}}
    write_json(args.report, report)
    if not args.execute:
        print(json.dumps({"status": "prepared", "network_requests": 0}))
        return 0
    engine = RoutedLegacyEngine.__new__(RoutedLegacyEngine)
    engine.vector_fields = {"indexes.embedding": 1024}
    groups = copy.deepcopy(request["condition_dicts"])
    for group in groups:
        group.setdefault("audit_result", [1, 2, -1])
    query = {"query": request["text"], "attribute": groups, "vector": {"value": fixed["vector"]}}
    dsls = {route: engine._build_search_query(query, include_text=route == "bm25", include_vector=route == "vector",
                                            vector_k=10, vector_boost=2.0 if route == "vector" else 1.0)
            for route in ("bm25", "vector")}
    target = NewTarget(endpoint)
    def one_round(mode):
        stages = []
        wall_start = time.perf_counter()
        for index in INDICES:
            for route, dsl in dsls.items():
                start = time.perf_counter()
                body = target.call("POST", f"/{index}/_search",
                    params={"search_type": mode, "preference": args.preference,
                            "ignore_unavailable": "true", "allow_no_indices": "true"},
                    json={"query": dsl, "size": 10, "_source": False})
                stages.append({"index": index, "route": route, "elapsed_ms": (time.perf_counter() - start) * 1000,
                    "took_ms": body.get("took"), "_shards": body.get("_shards"),
                    "candidate_id_order_sha256": digest([(hit["_index"], hit["_id"]) for hit in body["hits"]["hits"]]),
                    "scores_sha256": digest([hit["_score"] for hit in body["hits"]["hits"]])})
        return {"elapsed_ms": (time.perf_counter() - wall_start) * 1000, "stages": stages}
    modes = list(report["rounds"])
    report["status"] = "warming"
    for mode in modes:
        report.setdefault("warmup", {})[mode] = one_round(mode)
    write_json(args.report, report)
    for repeat in range(args.repeats):
        for mode in modes if repeat % 2 == 0 else modes[::-1]:
            row = one_round(mode)
            row["round"] = repeat
            report["rounds"][mode].append(row)
            report["status"] = "measuring"
            write_json(args.report, report)
    report["summary"] = {}
    for mode, rows in report["rounds"].items():
        durations = [row["elapsed_ms"] for row in rows]
        report["summary"][mode] = {"rounds": len(rows), "median_ms": statistics.median(durations),
            "mean_ms": statistics.mean(durations), "min_ms": min(durations), "max_ms": max(durations),
            "stage_median_ms": {f"{index}:{route}": statistics.median(stage["elapsed_ms"] for row in rows
                for stage in row["stages"] if stage["index"] == index and stage["route"] == route)
                for index in INDICES for route in dsls}}
    qtf, dfs = report["summary"][modes[0]], report["summary"][modes[1]]
    report.update(status="complete", finished_at=now(),
        median_added_dfs_ms=dfs["median_ms"] - qtf["median_ms"],
        median_dfs_to_qtf_ratio=dfs["median_ms"] / qtf["median_ms"],
        new_search_requests=8 + 8 * args.repeats)
    write_json(args.report, report)
    print(json.dumps({"status": "complete", "summary": report["summary"],
                      "median_added_dfs_ms": report["median_added_dfs_ms"],
                      "median_dfs_to_qtf_ratio": report["median_dfs_to_qtf_ratio"]}), flush=True)
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
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.indices = None
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
