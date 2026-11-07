#!/usr/bin/env python3
"""Read-only legacy /search versus local ES8 /search regression.

Cases hold private query text locally; the report contains only hashes, IDs,
scores and public request settings. The old responses can be reused while the
new implementation is repaired. No agents, writes or Elasticsearch scrolls run.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_es7_es8_online import iter_dump_records, sha256_json

KEY_INDICES = ("mercado", "wayfair", "mercado_local", "payoneer", "payoneer_olive")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, body: Mapping[str, Any], private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    if private:
        temporary.chmod(0o600)
    temporary.replace(path)


def request_profile(kind: str) -> Dict[str, Any]:
    return {
        "search_type": kind, "score_threshold": 0.4,
        "top_k": 40 if kind == "qa" else 10, "data_type": "text",
        "condition_dicts": ([{"audit_result": [1, 2], "data_type": ["qa"]}]
                           if kind == "qa" else [{"data_type": "segment"}]),
    }


def build_cases(dump_dir: Path, stage_log: Optional[Path]) -> Dict[str, Any]:
    states = {s["source_index"]: s for f in (dump_dir / "states").glob("*.json")
              if (s := read_json(f)).get("source_index")}
    cases = []
    for index in KEY_INDICES:
        state = states[index]
        fixtures = {}
        for offset, record in enumerate(iter_dump_records(Path(state["file"]))):
            source = record["_source"]
            if source.get("del_flag") not in (0, "0"):
                continue
            kind = str(source.get("data_type") or "")
            if kind == "qa" and source.get("audit_result") in (1, 2, "1", "2") and source.get("title"):
                fixtures.setdefault("qa", record)
            if kind == "segment" and source.get("audit_result") in (1, 2, -1, "1", "2", "-1") and source.get("content"):
                fixtures.setdefault("segment", record)
            if len(fixtures) == 2 or offset >= 2000:
                break
        if "qa" not in fixtures:
            raise RuntimeError(f"no eligible QA fixture in bounded prefix: {index}")
        for kind, synonyms in (("qa", True), ("qa", False), ("segment", True)):
            fixture = fixtures.get(kind) or fixtures["qa"]
            query = str(fixture["_source"].get("title") or "") if kind == "qa" else str(fixture["_source"].get("content") or "")[:256]
            body = {**request_profile(kind), "text": query, "index_names": index, "use_synonyms": synonyms}
            cases.append({
                "name": f"fixture:{index}:{kind}:synonyms={synonyms}", "body": body,
                "provenance": {
                    "kind": "production_parameter_shape_with_dump_query",
                    "fixture_id": str(fixture["_id"]), "dump_file": state["file"],
                    "eligible_profile_fixture_found": kind in fixtures,
                },
            })
    if stage_log and stage_log.exists():
        for row in read_json(stage_log):
            if row.get("stage") != "knowledge_recall":
                continue
            data = json.loads(row["log_data"]) if isinstance(row.get("log_data"), str) else row["log_data"]
            if not data.get("search_query") or not data.get("conditions"):
                continue
            names = str(data.get("index_name") or "").split(",")
            if any(index not in states for index in names):
                continue
            body = copy.deepcopy(data["conditions"])
            body.update(text=data["search_query"], index_names=data["index_name"])
            body.setdefault("use_synonyms", True)
            dual = data.get("dual_query") or {}
            cases.append({
                "name": f"logged:{row['id']}:{body.get('search_type')}", "body": body,
                "provenance": {"kind": "logged_agent_recall_request", "log_file": str(stage_log),
                               "log_id": row["id"], "logged_at": str(row.get("create_time") or ""),
                               "dual_query_triggered": bool(dual.get("triggered")),
                               "replayed_component": "completed_query" if body["text"] == dual.get("completed_query") else "logged_search_query",
                               "historical_merged_recall_count": data.get("recall_count"),
                               "use_synonyms_inferred_from_client_default": "use_synonyms" not in data["conditions"]},
            })
    return {
        "created_at": now(), "profile_source": "/root/sell_agents/knowledge/kb_search_tool.py",
        "client_source": "/root/sell_agents/knowledge/knowledge_retriever.py", "cases": cases,
    }


def local_service_auth(port: str = "8012") -> Optional[tuple]:
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            argv = [p.decode(errors="replace") for p in (process / "cmdline").read_bytes().split(b"\0") if p]
            if "uvicorn" not in argv or port not in argv:
                continue
            environment = dict(p.split(b"=", 1) for p in (process / "environ").read_bytes().split(b"\0") if b"=" in p)
            user = environment.get(b"KDB_SEARCH_BASIC_USER")
            password = environment.get(b"KDB_SEARCH_BASIC_PASSWORD")
            if user and password:
                return user.decode(), password.decode()
        except (OSError, ValueError):
            continue
    return None


def logical_dataset(value: Any) -> str:
    return str(value or "").split("__v817_", 1)[0]


def response_summary(url: str, body: Mapping[str, Any], auth: Optional[tuple], timeout: float) -> Dict[str, Any]:
    started = time.monotonic()
    result: Dict[str, Any] = {"measured_at": now(), "basic_auth_used": auth is not None}
    try:
        response = requests.post(url, json=body, headers={"Content-Type": "application/json"},
                                 auth=auth, timeout=timeout)
        result.update(http_status=response.status_code, elapsed_seconds=round(time.monotonic() - started, 3))
        if response.status_code != 200:
            result["error_body_sha256"] = hashlib.sha256(response.content).hexdigest()
            result["results"] = []
            return result
        data = response.json()
        if "results" not in data:
            data = data.get("body", {})
            if isinstance(data, str):
                data = json.loads(data)
        rows = data.get("results") or []
        result["result_count"] = len(rows)
        result["results"] = [{
            "id": str(row.get("id") or row.get("_id") or ""),
            "dataset": logical_dataset(row.get("dataset")),
            "score": float(row.get("score") or 0.0),
            "text_fields_sha256": sha256_json({k: row.get(k) for k in ("q", "a", "content", "synonyms_title")}),
            "metadata_sha256": sha256_json({k: row.get(k) for k in ("ext_info", "metadata", "primary_category")}),
        } for row in rows]
    except Exception as exc:
        result.update(error_type=type(exc).__name__, elapsed_seconds=round(time.monotonic() - started, 3), results=[])
    return result


def compare(old: Mapping[str, Any], new: Mapping[str, Any], tolerance: float = 1e-5) -> Dict[str, Any]:
    a = {(r["dataset"], r["id"]): r for r in old.get("results", [])}
    b = {(r["dataset"], r["id"]): r for r in new.get("results", [])}
    shared = set(a) & set(b)
    old_order = [(r["dataset"], r["id"]) for r in old.get("results", [])]
    new_order = [(r["dataset"], r["id"]) for r in new.get("results", [])]
    maximum = max((abs(a[k]["score"] - b[k]["score"]) for k in shared), default=None)
    transport = old.get("http_status") == new.get("http_status") == 200
    text_differences = sum(a[k]["text_fields_sha256"] != b[k]["text_fields_sha256"] for k in shared)
    metadata_differences = sum(a[k]["metadata_sha256"] != b[k]["metadata_sha256"] for k in shared)
    return {
        "transport_pass": transport, "old_count": len(old_order), "new_count": len(new_order),
        "count_equal": len(old_order) == len(new_order), "id_set_equal": set(a) == set(b),
        "id_order_equal": old_order == new_order,
        "top1_same": bool(old_order and new_order and old_order[0] == new_order[0]),
        "top10_common_ids": len(set(old_order[:10]) & set(new_order[:10])),
        "common_ids": len(shared), "old_only_ids": [list(k) for k in sorted(set(a) - set(b))],
        "new_only_ids": [list(k) for k in sorted(set(b) - set(a))],
        "common_score_max_abs_diff": maximum, "common_text_field_differences": text_differences,
        "common_metadata_differences": metadata_differences,
        "strict_parity_pass": transport and bool(a) and old_order == new_order
                             and maximum is not None and maximum <= tolerance
                             and not text_differences and not metadata_differences,
        "empty_case": transport and not old_order and not new_order,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--build-cases", action="store_true")
    parser.add_argument("--dump-dir", type=Path, default=Path("migration_runs/local_dump_20261001/data"))
    parser.add_argument("--stage-log", type=Path)
    parser.add_argument("--old-url", default="http://120.77.147.247:8003/search")
    parser.add_argument("--new-url", default="http://127.0.0.1:8012/search")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--reuse-old-report", type=Path)
    parser.add_argument("--require-old-cache", action="store_true", help="fail before requests unless every selected old response is cached successfully")
    parser.add_argument("--old-only", action="store_true")
    parser.add_argument("--new-no-auth", action="store_true", help="replay the existing agent client's lack of Basic authorization")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--names", nargs="*", default=[])
    args = parser.parse_args()
    if args.build_cases:
        bundle = build_cases(args.dump_dir, args.stage_log)
        write_json(args.cases, bundle, private=True)
        print(json.dumps({"cases_file": str(args.cases), "case_count": len(bundle["cases"]),
                          "logged_cases": sum(c["provenance"]["kind"] == "logged_agent_recall_request" for c in bundle["cases"]) }))
        if not args.report:
            return 0
    if not args.report:
        parser.error("--report is required for HTTP comparisons")
    cases = read_json(args.cases)["cases"]
    if args.names:
        cases = [c for c in cases if c["name"] in args.names]
    if not cases:
        raise ValueError("no selected cases")
    cache = read_json(args.reuse_old_report) if args.reuse_old_report else {}
    if cache and cache.get("old_url") != args.old_url:
        raise ValueError("cached old response URL differs")
    old_by_name = {c["name"]: c for c in cache.get("cases", [])}
    if args.require_old_cache:
        for case in cases:
            previous = old_by_name.get(case["name"])
            if not previous or previous.get("old", {}).get("http_status") != 200:
                raise ValueError(f"successful old cache required: {case['name']}")
            if previous.get("request_sha256") != sha256_json(case["body"]):
                raise ValueError(f"cached request differs: {case['name']}")
    auth = None if args.old_only or args.new_no_auth else local_service_auth()
    report: Dict[str, Any] = {
        "started_at": now(), "old_url": args.old_url, "new_url": args.new_url,
        "read_only": True, "agents_run": False, "cases": [],
    }
    for case in cases:
        body = case["body"]
        fingerprint = sha256_json(body)
        previous = old_by_name.get(case["name"])
        if previous and previous.get("request_sha256") != fingerprint:
            raise ValueError(f"cached request differs: {case['name']}")
        old = previous["old"] if previous and previous.get("old", {}).get("http_status") == 200 else response_summary(args.old_url, body, None, args.timeout)
        entry = {
            "name": case["name"], "provenance": case["provenance"], "request_sha256": fingerprint,
            "request": {
                "index_names": body["index_names"], "top_k": body.get("top_k", 100),
                "score_threshold": body.get("score_threshold", -1), "search_type": body.get("search_type", "qa"),
                "use_synonyms": body.get("use_synonyms", False), "query_chars": len(body["text"]),
                "query_sha256": hashlib.sha256(body["text"].encode()).hexdigest(),
                "condition_group_fields": [list(group) for group in body.get("condition_dicts") or []],
                "conditions_sha256": sha256_json(body.get("condition_dicts")),
            }, "old": old, "old_reused": previous is not None and old is previous.get("old"),
        }
        if not args.old_only:
            entry["new"] = response_summary(args.new_url, body, auth, args.timeout)
            entry["comparison"] = compare(old, entry["new"])
        report["cases"].append(entry)
        write_json(args.report, report)
        progress = {"case": case["name"], "old_status": old.get("http_status"), "old_count": old.get("result_count")}
        if "comparison" in entry:
            progress.update(entry["comparison"])
        print(json.dumps(progress, ensure_ascii=False), flush=True)
    report["finished_at"] = now()
    report["summary"] = {
        "case_count": len(report["cases"]), "old_reused": sum(c["old_reused"] for c in report["cases"]),
        "old_only": args.old_only,
        "strict_parity_pass": False if args.old_only else all(c["comparison"]["strict_parity_pass"] for c in report["cases"]),
        "transport_failures": sum(c["old"].get("http_status") != 200 or not args.old_only and c["new"].get("http_status") != 200 for c in report["cases"]),
    }
    write_json(args.report, report)
    print(json.dumps({"report": str(args.report), "summary": report["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
