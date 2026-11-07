#!/usr/bin/env python3
"""Read-only restored Wayfair private-index and union-request acceptance.

Default mode prepares private requests and a sanitized plan, with zero network.
--wait runs data/native probes after the standalone priority restore completes,
then replays unions only after both entries are complete in partition states.
Old requests are never sent: only a matching full-request-hash cache is reused.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_key3_restored_data import NewTarget, document_check, sample_base, valid_vector, digest
from audit_missing_indices_http import response_summary
from audit_all81_restored_counts import validate_expected
from compare_es7_es8_online import sha256_json
from compare_legacy_search_http import logical_dataset, now, read_json, write_json
from restore_local_root_vectors import load_inputs

WAYFAIR = "wayfair"
PRIVATE = "wayfair_wayfair_test2"
ROOTS = ("title_embedding", "content_embedding")


class JointFailure(RuntimeError):
    pass


def source_cache_rows(cache):
    entries = cache.get("cases", {})
    if isinstance(entries, dict):
        return [{"name": name, **row} for name, row in entries.items()]
    return entries


def matching_old(body, cache):
    fingerprint = sha256_json(body)
    matches = []
    for row in source_cache_rows(cache):
        request = row.get("request", {})
        actual_hash = sha256_json(request) if "text" in request else row.get("request_sha256")
        if actual_hash != fingerprint:
            continue
        old = (row.get("runs") or {}).get("old") or row.get("old")
        if not old or old.get("http_status") != 200:
            continue
        rows = old.get("results")
        if not isinstance(rows, list):
            raise JointFailure("matching_old_cache_results_array_required")
        clean = []
        for item in rows:
            ident = str(item.get("id") or item.get("_id") or "")
            score = float(item["score"])
            if not ident or not math.isfinite(score):
                raise JointFailure("invalid_matching_old_result_identity_or_score")
            clean.append({"id": ident, "dataset": logical_dataset(item.get("dataset")), "score": score,
                          **{key: item[key] for key in ("text_fields_sha256", "metadata_sha256") if key in item}})
        matches.append({"http_status": 200, "result_count": len(clean), "results": clean,
                        "request_sha256": fingerprint, "cache_name": row.get("name"),
                        "elapsed_seconds": old.get("elapsed_s", old.get("elapsed_seconds"))})
    if len(matches) > 1 and len({sha256_json(m["results"]) for m in matches}) != 1:
        raise JointFailure("conflicting_matching_old_cached_results")
    return matches[0] if matches else None


def build_cases(fixture_bundle, real_cache):
    fixtures = {row["name"]: row for row in fixture_bundle["cases"]}
    real = {row["name"]: row for row in source_cache_rows(real_cache)}
    output = []
    for kind, synonyms, real_name in (("qa", True, "wayfair_qa_union"),
                                       ("qa", False, None),
                                       ("segment", True, "wayfair_segment_union")):
        row = real.get(real_name) if real_name else None
        names = f"{PRIVATE},{WAYFAIR}" if kind == "qa" else f"{WAYFAIR},{PRIVATE}"
        if row and "text" in row.get("request", {}):
            body = copy.deepcopy(row["request"])
            if body.get("index_names") != names or body.get("search_type") != kind or body.get("use_synonyms") is not synonyms:
                raise JointFailure("real_union_request_profile_or_index_order_differs")
            provenance = {"kind": "parent_captured_real_union_http_request", "cache_name": real_name}
            name = f"real:{real_name}"
        else:
            fixture = fixtures[f"fixture:wayfair:{kind}:synonyms={synonyms}"]
            body = copy.deepcopy(fixture["body"])
            body["index_names"] = names
            provenance = {"kind": "production_parameter_fixture_with_parent_required_joint_index_order",
                          "source_case": fixture["name"], "real_user_question": False}
            name = f"fixture:wayfair:{kind}:synonyms={synonyms}:union"
        output.append({"name": name, "body": body, "provenance": provenance})
    return output


def public_case(case, old):
    body = case["body"]
    return {"name": case["name"], "provenance": case["provenance"], "request_sha256": sha256_json(body),
            "index_names": body["index_names"], "search_type": body["search_type"],
            "score_threshold": body.get("score_threshold"), "top_k": body.get("top_k"),
            "use_synonyms": body.get("use_synonyms"), "query_chars": len(body["text"]),
            "query_sha256": hashlib.sha256(body["text"].encode()).hexdigest(),
            "condition_sha256": sha256_json(body.get("condition_dicts")),
            "old_cache_status": "matched_complete_request_hash" if old else "missing_cached_old",
            "old_count": old["result_count"] if old else None,
            "cached_old_content_hashes_available": bool(old and all("text_fields_sha256" in row and "metadata_sha256" in row
                                                                      for row in old["results"]))}


def compare_cached(old, new):
    if not old:
        return {"old_cache_status": "missing_cached_old", "old_comparison_executed": False,
                "parity_pass": None, "new_transport_pass": new.get("http_status") == 200
                and new.get("response_schema_valid") is True, "new_count": new.get("result_count")}
    a = [(row["dataset"], row["id"]) for row in old["results"]]
    b = [(row["dataset"], row["id"]) for row in new.get("results", [])]
    old_by_id = {(row["dataset"], row["id"]): row for row in old["results"]}
    new_by_id = {(row["dataset"], row["id"]): row for row in new.get("results", [])}
    common = set(old_by_id) & set(new_by_id)
    error = max((abs(old_by_id[key]["score"] - new_by_id[key]["score"]) for key in common), default=None)
    hashes_covered = bool(a) and all("text_fields_sha256" in row and "metadata_sha256" in row for row in old["results"])
    hash_differences = sum(any(old_by_id[key][field] != new_by_id[key][field] for field in ("text_fields_sha256", "metadata_sha256"))
                           for key in common) if hashes_covered else None
    transport = old["http_status"] == new.get("http_status") == 200 and new.get("response_schema_valid") is True
    rank_score_pass = transport and bool(a) and a == b and error is not None and error <= 1e-6
    return {"old_cache_status": "matched_complete_request_hash", "old_comparison_executed": True,
            "transport_pass": transport, "old_count": len(a), "new_count": len(b), "count_equal": len(a) == len(b),
            "id_set_equal": set(a) == set(b), "id_order_equal": a == b,
            "top1_same": bool(a and b and a[0] == b[0]), "top2_same": bool(a and b and a[:2] == b[:2]),
            "top10_common_ids": len(set(a[:10]) & set(b[:10])), "common_ids": len(common),
            "old_only_ids": [list(key) for key in sorted(set(a) - set(b))],
            "new_only_ids": [list(key) for key in sorted(set(b) - set(a))],
            "common_score_max_abs_diff": error, "rank_score_parity_pass": rank_score_pass,
            "old_content_hash_coverage": hashes_covered, "common_hash_differences": hash_differences,
            "parity_pass": rank_score_pass and hash_differences == 0 if hashes_covered else None}


def checkpoint_ready(path, names, source_args, endpoint, expected_counts):
    if not path.exists():
        return False
    state = read_json(path)
    if state.get("apply") is not True or state.get("status") in {"failed", "partitioned"}:
        return False
    subset_args = copy.copy(source_args)
    subset_args.indices = names
    _, _, _, _, identity = load_inputs(subset_args)
    identity.update(endpoint_sha256=digest(endpoint.get("hosts") or endpoint.get("host")), apply=True)
    if state.get("job_sha256") != digest(identity):
        raise JointFailure("restore_checkpoint_input_or_endpoint_mismatch")
    for name, wanted in expected_counts.items():
        progress = state.get("indices", {}).get(name, {})
        if not progress.get("complete") or progress.get("counts_after") != wanted or progress.get("skips"):
            return False
    return True


def readiness(args, endpoint, expected):
    priority_ready = checkpoint_ready(args.priority_state, [PRIVATE], args, endpoint, {PRIVATE: expected[PRIVATE]})
    manifest = read_json(args.restore_manifest)
    partition_ready = False
    for group in manifest["groups"].values():
        if {WAYFAIR, PRIVATE} <= set(group["indices"]):
            partition_ready = checkpoint_ready(Path(group["state"]), group["indices"], args, endpoint,
                                                 {WAYFAIR: expected[WAYFAIR], PRIVATE: expected[PRIVATE]})
    return priority_ready or partition_ready, partition_ready


def local_samples(args, expected_counts):
    subset_args = copy.copy(args)
    subset_args.indices = [PRIVATE]
    _, selected, baseline, overrides, _ = load_inputs(subset_args)
    base = baseline[PRIVATE]
    if Path(base["file"]).resolve() != Path(selected[PRIVATE]["dump_file"]).resolve():
        raise JointFailure("private_base_path_differs_from_plan")
    if overrides[PRIVATE]:
        raise JointFailure("private_delta_requires_additional_sampling_support")
    count = int(base["docs_exported"])
    if count != expected_counts["docs"]:
        raise JointFailure("private_local_doc_count_differs_from_expected")
    quota = min(100, count)
    samples, info = sample_base(Path(base["file"]), base["sha256"], count, quota, {}, 0)
    return samples, info


def audit_data(target, samples, expected):
    mapping, actual = target.mapping(PRIVATE), target.counts(PRIVATE)
    docs = []
    for start in range(0, len(samples), 32):
        batch = samples[start:start + 32]
        current, vectors = target.read(PRIVATE, [str(sample["record"]["_id"]) for sample in batch])
        docs.extend(document_check(sample, current.get(str(sample["record"]["_id"])), vectors.get(str(sample["record"]["_id"]), {}))
                    for sample in batch)
    return {"expected_counts": expected, "target_counts": actual, "counts_equal": actual == expected,
            "mapping": mapping, "samples": len(samples), "sample_passed": sum(row["passed"] for row in docs),
            "documents": docs, "passed": bool(samples) and actual == expected and mapping["root_mapping_pass"]
            and mapping["source_enabled"] and all(row["passed"] for row in docs)}


def native_probe(target, samples, field, expected_count):
    anchor = next((sample["record"] for sample in samples if valid_vector(sample["record"]["_source"].get(field))), None)
    if not anchor:
        return {"field": field, "status": "no_sample_anchor", "expected_indexed_count": expected_count,
                "passed": expected_count == 0, "coverage_gap": expected_count > 0}
    ident, vector = str(anchor["_id"]), anchor["_source"][field]
    output = {"field": field, "query_id": ident, "query_vector_sha256": digest(vector), "query_dims": len(vector),
              "operator": "native_knn", "num_candidates": 100, "runs": {}}
    try:
        for label, k, filtered in (("global", 5, False), ("self_filtered", 1, True)):
            clause = {"field": field, "query_vector": vector, "k": k, "num_candidates": 100}
            if filtered:
                clause["filter"] = {"ids": {"values": [ident]}}
            body = target.call("POST", f"/{PRIVATE}/_search", json={"size": k, "_source": False, "query": {"knn": clause}})
            hits = body.get("hits", {}).get("hits", [])
            clean = [{"id": str(hit["_id"]), "index": str(hit["_index"]), "score": float(hit["_score"])} for hit in hits]
            output["runs"][label] = {"results": clean, "source_id_recalled": any(hit["id"] == ident and hit["index"] == PRIVATE for hit in clean),
                                     "passed": bool(clean) and all(hit["index"] == PRIVATE and math.isfinite(hit["score"]) for hit in clean)
                                     and clean[0]["score"] >= 0.9999
                                     and (not filtered or clean[0]["id"] == ident)}
        output.update(status="complete", passed=all(run["passed"] for run in output["runs"].values()))
    except Exception as exc:
        output.update(status="failed", passed=False, error_type=type(exc).__name__)
    return output


def run(args):
    real_cache = read_json(args.old_cache) if args.old_cache.exists() else {"cases": {}}
    cases = build_cases(read_json(args.source_cases), real_cache)
    if args.private_cases.exists():
        previous = read_json(args.private_cases)
        if sha256_json(previous["cases"]) != sha256_json(cases):
            raise JointFailure("private_case_file_differs_from_prepared_input")
    else:
        write_json(args.private_cases, {"created_at": now(), "cases": cases}, private=True)
    cached = {case["name"]: matching_old(case["body"], real_cache) for case in cases}
    plan = [public_case(case, cached[case["name"]]) for case in cases]
    expected_artifact = read_json(args.expected)
    names, _, _, _, input_identity = load_inputs(args)
    validate_expected(expected_artifact, names, input_identity)
    expected = {name: expected_artifact["indices"][name]["counts"] for name in (WAYFAIR, PRIVATE)}
    config = read_json(args.target_config)
    if str(config.get("es_version")) != "8.17":
        raise JointFailure("target_config_not_es817")
    endpoint = config["providers"]["serverless"]
    job_sha = digest({"case_request_hashes": [item["request_sha256"] for item in plan],
                      "old_cached_result_hashes": {name: digest(old) for name, old in cached.items()},
                      "expected_counts_sha256": expected_artifact["content_sha256"], "new_url": args.new_url,
                      "endpoint_sha256": digest(endpoint.get("hosts") or endpoint.get("host"))})
    report = read_json(args.report) if args.report.exists() else {
        "started_at": now(), "job_sha256": job_sha, "read_only": True, "reads_old_es": False,
        "reads_old_http": False, "agents_run": False, "private_index": PRIVATE, "expected_counts": expected,
        "plan": plan, "joint_cases": []}
    if report.get("job_sha256") != job_sha:
        raise JointFailure("previous_joint_report_request_or_expected_inputs_changed")
    report.update(pid=os.getpid(), mode="wait_then_execute" if args.wait else "execute" if args.execute else "dry_run",
                  private_cases_file=str(args.private_cases), old_cache_file=str(args.old_cache), resumed_at=now())
    if not args.execute and not args.wait:
        if report.get("data_acceptance") or report.get("joint_cases"):
            raise JointFailure("dry_run_cannot_overwrite_live_acceptance_report")
        report.update(status="prepared", network_requests=0)
        write_json(args.report, report)
        print(json.dumps({"status": "prepared", "cases": len(cases), "missing_cached_old": [p["name"] for p in plan
                                       if p["old_cache_status"] == "missing_cached_old"], "network_requests": 0}))
        return 0
    parsed = urlparse(args.new_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8012 or parsed.path != "/search":
        raise JointFailure("only_localhost_8012_search_allowed")
    started = time.monotonic()
    while True:
        data_ready, joint_ready = readiness(args, endpoint, expected)
        report.update(data_restore_ready=data_ready, partition_union_restore_ready=joint_ready, last_checked_at=now())
        probes = report.setdefault("native_root_probes", {})
        if data_ready and ("data_acceptance" not in report or any(field not in probes for field in ROOTS)):
            samples, sample_info = local_samples(args, expected[PRIVATE])
            target = NewTarget(endpoint)
            report["local_sampling"] = sample_info
            if "data_acceptance" not in report:
                report["data_acceptance"] = audit_data(target, samples, expected[PRIVATE])
                write_json(args.report, report)
            for field in ROOTS:
                if field in probes:
                    continue
                probes[field] = native_probe(target, samples, field, expected[PRIVATE][field])
                write_json(args.report, report)
            print(json.dumps({"private_data_samples": len(samples), "data_passed": report["data_acceptance"]["passed"],
                              "native_passed": all(p["passed"] for p in report["native_root_probes"].values())}), flush=True)
        if joint_ready:
            done = {row["request"]["name"] for row in report["joint_cases"]}
            for case in cases:
                if case["name"] in done:
                    continue
                new = response_summary(args.new_url, case["body"], None, 30)
                old = cached[case["name"]]
                entry = {"request": public_case(case, old), "old_cached": old, "new": new,
                         "comparison": compare_cached(old, new)}
                report["joint_cases"].append(entry)
                write_json(args.report, report)
                print(json.dumps({"joint_case": case["name"], "new_http_status": new.get("http_status"),
                                  "new_count": new.get("result_count"), "comparison": entry["comparison"]}), flush=True)
            matched = [row for row in report["joint_cases"] if row["old_cached"]]
            report.update(status="complete", finished_at=now(),
                          new_data_native_pass=report["data_acceptance"]["passed"] and all(p["passed"] for p in report["native_root_probes"].values()),
                          new_joint_transport_pass=all(row["new"].get("http_status") == 200
                              and row["new"].get("response_schema_valid") is True
                              and row["new"].get("result_count", 0) > 0 for row in report["joint_cases"]),
                          cached_old_rank_score_parity_pass=bool(matched) and all(row["comparison"]["rank_score_parity_pass"] for row in matched),
                          missing_cached_old=[row["request"]["name"] for row in report["joint_cases"] if not row["old_cached"]],
                          old_content_parity_covered=bool(matched) and all(row["comparison"].get("old_content_hash_coverage", False) for row in matched))
            write_json(args.report, report)
            return 0 if report["new_data_native_pass"] and report["new_joint_transport_pass"] else 2
        report["status"] = "waiting_union_restore" if "data_acceptance" in report else "waiting_private_restore"
        write_json(args.report, report)
        if not args.wait:
            return 3
        if time.monotonic() - started >= args.max_wait_seconds:
            report.update(status="timeout", finished_at=now())
            write_json(args.report, report)
            return 3
        time.sleep(args.poll_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--wait", action="store_true")
    parser.add_argument("--source-cases", type=Path, default=Path("/tmp/kdb_http_parity_cases_20261004.json"))
    parser.add_argument("--old-cache", type=Path, default=Path("/tmp/sg_mercado_local_wayfair_union_compare_20261004.json"))
    parser.add_argument("--private-cases", type=Path, default=Path("/tmp/kdb_wayfair_joint_cases_20261004.json"))
    parser.add_argument("--expected", type=Path, default=Path("artifacts/all81_expected_root_counts_20261004.json"))
    parser.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    parser.add_argument("--priority-state", type=Path, default=Path("artifacts/root_restore_priority_wayfair_joint_20261004.json"))
    parser.add_argument("--target-config", type=Path, default=Path("config/config_es_runtime.local.json"))
    parser.add_argument("--new-url", default="http://127.0.0.1:8012/search")
    parser.add_argument("--shard-plan", default="migration_runs/local_dump_20261001/data/shard_plan_1g.json")
    parser.add_argument("--dump-dir", default="migration_runs/local_dump_20261001/data")
    parser.add_argument("--incremental-manifest", default="migration_runs/incremental_local_20261002T161500Z/manifest.json")
    parser.add_argument("--incremental-report", default="migration_runs/incremental_local_20261002T161500Z/import_report.json")
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--max-wait-seconds", type=float, default=14400)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    args.indices = None
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc) if isinstance(exc, JointFailure) else type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
