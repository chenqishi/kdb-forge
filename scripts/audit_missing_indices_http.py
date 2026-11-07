#!/usr/bin/env python3
"""Compare new localhost /search baselines with synthetic missing-index requests.

Default mode writes only a sanitized plan. --execute reads only new ES HEAD
metadata and new localhost HTTP. This sends already expanded synthetic names;
it does not run the agent's client_user index resolution or any old endpoint.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

import requests

from compare_es7_es8_online import sha256_json
from compare_legacy_search_http import compare, logical_dataset, now, read_json, write_json
from migrate_es7_to_es8 import ESHttp, index_provider
from retest_restored_http_cases import aggregate_restore, restore_inputs

FIXTURE = "fixture:payoneer:qa:synonyms=True"
ADMIN = "mercado_local_mercado_local_admin"
LITERAL_PRIVATE = "private"
SERVERLESS_PRIVATE = "private_kdb_compat_absent_20261004"
PAAS_PRIVATE = "payoneer_private_kdb_compat_absent_20261004"


class CompatFailure(RuntimeError):
    pass


def build_cases(bundle: dict) -> list[dict]:
    candidates = [case for case in bundle["cases"] if case["name"] == FIXTURE]
    if len(candidates) != 1:
        raise CompatFailure("unique_payoneer_qa_fixture_required")
    original = candidates[0]["body"]
    specs = [
        ("baseline:paas", ["payoneer"], "paas", None),
        ("baseline:cross_provider", ["payoneer", ADMIN], "cross", None),
    ]
    for label, missing in (("literal_private", LITERAL_PRIVATE),
                           ("expanded_serverless_private", SERVERLESS_PRIVATE),
                           ("expanded_paas_private", PAAS_PRIVATE)):
        specs.extend((
            (f"mixed:{label}:first", [missing, "payoneer"], "paas", "baseline:paas"),
            (f"mixed:{label}:last", ["payoneer", missing], "paas", "baseline:paas"),
        ))
    for label, missing in (("literal_private", LITERAL_PRIVATE), ("expanded_serverless_private", SERVERLESS_PRIVATE)):
        specs.extend((
            (f"mixed:cross_provider:{label}:first", [missing, "payoneer", ADMIN], "cross", "baseline:cross_provider"),
            (f"mixed:cross_provider:{label}:last", ["payoneer", ADMIN, missing], "cross", "baseline:cross_provider"),
        ))
    for label, names in (
        ("literal_private", [LITERAL_PRIVATE]),
        ("expanded_serverless_private", [SERVERLESS_PRIVATE]),
        ("expanded_paas_private", [PAAS_PRIVATE]),
        ("pair_serverless_paas", [SERVERLESS_PRIVATE, PAAS_PRIVATE]),
        ("pair_paas_serverless", [PAAS_PRIVATE, SERVERLESS_PRIVATE]),
    ):
        specs.append((f"empty:{label}", names, "paas", "empty"))
    cases = []
    for name, indices, section, baseline in specs:
        body = copy.deepcopy(original)
        body["index_names"] = ",".join(indices)
        cases.append({"name": name, "body": body, "section": section,
                      "baseline": baseline, "expected": "http_200_empty" if baseline == "empty" else
                      "http_200_nonempty" if baseline is None else "same_as_new_baseline"})
    return cases


def request_info(case: dict) -> dict:
    body = case["body"]
    return {"name": case["name"], "section": case["section"], "baseline": case["baseline"],
            "expected": case["expected"], "index_names": body["index_names"],
            "search_type": body.get("search_type"), "top_k": body.get("top_k"),
            "score_threshold": body.get("score_threshold"), "use_synonyms": body.get("use_synonyms"),
            "query_chars": len(body["text"]), "query_sha256": hashlib.sha256(body["text"].encode()).hexdigest(),
            "condition_sha256": sha256_json(body.get("condition_dicts")), "request_sha256": sha256_json(body)}


def verify_missing_names(config: dict, names: set[str]) -> list[dict]:
    clients = {}
    result = []
    for name in sorted(names):
        provider = index_provider(name)
        if provider not in clients:
            clients[provider] = ESHttp(config["providers"][provider], timeout=30)
        try:
            response = clients[provider].request("HEAD", f"/{name}")
        except Exception as exc:
            raise CompatFailure(f"missing_index_head_transport_{type(exc).__name__}") from None
        if response.status_code != 404:
            raise CompatFailure(f"synthetic_missing_index_not_404:{name}:{response.status_code}")
        result.append({"index": name, "provider": provider, "http_status": 404, "exists": False})
    return result


def response_summary(url: str, body: dict, auth, timeout: float) -> dict:
    if auth is not None:
        raise CompatFailure("anonymous_client_required")
    started = time.monotonic()
    result = {"measured_at": now(), "basic_auth_used": False, "results": []}
    try:
        response = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=timeout)
        result.update(http_status=response.status_code, elapsed_seconds=round(time.monotonic() - started, 3))
        if response.status_code != 200:
            result["error_body_sha256"] = hashlib.sha256(response.content).hexdigest()
            return result
        payload = response.json()
        if not isinstance(payload, dict):
            raise CompatFailure("response_object_required")
        if "results" not in payload:
            payload = payload.get("body")
            if isinstance(payload, str):
                payload = json.loads(payload)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise CompatFailure("response_results_array_required")
        rows = payload["results"]
        if any(not isinstance(row, dict) for row in rows):
            raise CompatFailure("invalid_result_row_shape")
        result.update(response_schema_valid=True, result_count=len(rows), results=[{
            "id": str(row.get("id") or row.get("_id") or ""), "dataset": logical_dataset(row.get("dataset")),
            "score": float(row.get("score") or 0),
            "text_fields_sha256": sha256_json({key: row.get(key) for key in ("q", "a", "content", "synonyms_title")}),
            "metadata_sha256": sha256_json({key: row.get(key) for key in ("ext_info", "metadata", "primary_category")}),
        } for row in rows])
    except Exception as exc:
        result.update(error_type=str(exc) if isinstance(exc, CompatFailure) else type(exc).__name__,
                      response_schema_valid=False, elapsed_seconds=round(time.monotonic() - started, 3))
    return result


def evaluate(case: dict, response: dict, baselines: dict) -> dict:
    if response.get("response_schema_valid") is not True:
        return {"http_status": response.get("http_status"), "passed": False, "response_schema_valid": False}
    if case["baseline"] == "empty":
        return {"http_status": response.get("http_status"), "result_count": response.get("result_count"),
                "passed": response.get("http_status") == 200 and response.get("result_count") == 0
                          and response.get("results") == [], "expected_empty": True}
    if case["baseline"] is None:
        return {"http_status": response.get("http_status"), "result_count": response.get("result_count"),
                "passed": response.get("http_status") == 200 and bool(response.get("results")),
                "required_nonempty_baseline": True}
    baseline = baselines.get(case["baseline"])
    if baseline is None:
        raise CompatFailure("baseline_response_not_available")
    comparison = compare(baseline, response, tolerance=1e-6)
    # These names refer to two new endpoint requests, never old ES/HTTP.
    return {"passed": comparison["strict_parity_pass"], "transport_pass": comparison["transport_pass"],
            "baseline_count": comparison["old_count"], "mixed_count": comparison["new_count"],
            "count_equal": comparison["count_equal"], "id_set_equal": comparison["id_set_equal"],
            "id_order_equal": comparison["id_order_equal"], "top1_same": comparison["top1_same"],
            "common_ids": comparison["common_ids"], "baseline_only_ids": comparison["old_only_ids"],
            "mixed_only_ids": comparison["new_only_ids"],
            "common_score_max_abs_diff": comparison["common_score_max_abs_diff"],
            "common_text_field_differences": comparison["common_text_field_differences"],
            "common_metadata_differences": comparison["common_metadata_differences"]}


def run(args) -> int:
    cases = build_cases(read_json(args.cases))
    if args.section != "all":
        cases = [case for case in cases if case["section"] == args.section]
    report = {"started_at": now(), "mode": "execute" if args.execute else "dry_run", "read_only": True,
              "reads_old_es": False, "reads_old_http": False, "agents_run": False,
              "real_client_user_resolution_run": False, "fixture_case": FIXTURE,
              "provenance": "direct_http_requests_with_literal_and_already_expanded_synthetic_private_index_names",
              "new_url": args.new_url, "anonymous_localhost_client": True, "plan": [request_info(c) for c in cases],
              "cases": [], "status": "prepared"}
    write_json(args.report, report)
    if not args.execute:
        report.update(finished_at=now(), network_requests=0)
        write_json(args.report, report)
        print(json.dumps({"report": str(args.report), "status": "prepared", "case_count": len(cases), "network_requests": 0}))
        return 0
    try:
        parsed = urlparse(args.new_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 8012 or parsed.path != "/search":
            raise CompatFailure("only_localhost_8012_search_allowed")
        if any(ADMIN in case["body"]["index_names"].split(",") for case in cases):
            paths = restore_inputs(None, args.restore_manifest)
            indices, statuses = aggregate_restore(paths)
            if "failed" in statuses.values() or not indices.get(ADMIN, {}).get("complete") or not indices[ADMIN].get("counts_after"):
                raise CompatFailure("cross_provider_admin_restore_not_complete")
            report["restore_inputs"] = [str(path) for path in paths]
        config = read_json(args.target_config)
        if str(config.get("es_version")) != "8.17":
            raise CompatFailure("target_config_not_es817")
        missing = {name for case in cases for name in case["body"]["index_names"].split(",")
                   if name not in {"payoneer", ADMIN}}
        report["verified_missing_names"] = verify_missing_names(config, missing)
        report["status"] = "checking"
        write_json(args.report, report)
        baselines = {}
        for case in cases:
            response = response_summary(args.new_url, case["body"], None, args.timeout)
            if case["baseline"] is None:
                baselines[case["name"]] = response
            entry = {"request": request_info(case), "response": response,
                     "comparison": evaluate(case, response, baselines)}
            report["cases"].append(entry)
            write_json(args.report, report)
            print(json.dumps({"case": case["name"], "http_status": response.get("http_status"),
                              "count": response.get("result_count"), "passed": entry["comparison"]["passed"]}), flush=True)
        report.update(status="complete", finished_at=now(), all_pass=all(c["comparison"]["passed"] for c in report["cases"]))
        write_json(args.report, report)
        return 0 if report["all_pass"] else 2
    except Exception as exc:
        report.update(status="failed", error=str(exc) if isinstance(exc, CompatFailure) else type(exc).__name__, failed_at=now())
        write_json(args.report, report)
        print(json.dumps({"status": "failed", "error": report["error"]}), flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--section", choices=("all", "paas", "cross"), default="all")
    parser.add_argument("--cases", type=Path, default=Path("/tmp/kdb_http_parity_cases_20261004.json"))
    parser.add_argument("--new-url", default="http://127.0.0.1:8012/search")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--target-config", type=Path, default=Path("config/config_es_runtime.local.json"))
    parser.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    parser.add_argument("--report", type=Path, required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
