#!/usr/bin/env python3
"""Wait for per-index restore completion, then compare new HTTP to old cache."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from compare_legacy_search_http import now, read_json, write_json
from compare_es7_es8_online import sha256_json


def restore_inputs(state_path: Path | None, manifest_path: Path | None) -> list[Path]:
    if state_path is not None:
        return [state_path.resolve()]
    manifest = read_json(manifest_path)
    paths = [Path(group["state"]).resolve() for group in manifest["groups"].values()]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("restore manifest has empty or duplicate state paths")
    return paths


def aggregate_restore(paths: list[Path]) -> tuple[dict, dict]:
    indices = {}
    statuses = {}
    for path in paths:
        state = read_json(path)
        statuses[str(path)] = state.get("status")
        for name, progress in state["indices"].items():
            if name in indices:
                raise ValueError(f"index occurs in multiple restore partitions: {name}")
            indices[name] = progress
    return indices, statuses


def completed_report(path: Path, names: list[str], cases_by_name: dict) -> dict | None:
    if not path.exists():
        return None
    report = read_json(path)
    rows = report.get("cases", [])
    if not report.get("finished_at") or sorted(r["name"] for r in rows) != sorted(names):
        raise ValueError(f"unfinished comparison report requires inspection: {path}")
    for row in rows:
        if row.get("request_sha256") != sha256_json(cases_by_name[row["name"]]["body"]):
            raise ValueError(f"previous comparison request differs: {row['name']}")
        if not row.get("old_reused") or "new" not in row:
            raise ValueError(f"previous comparison did not reuse old cache: {row['name']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--restore-state", type=Path)
    source.add_argument("--restore-manifest", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--old-cache", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--poll-seconds", type=float, default=15)
    parser.add_argument("--max-wait-seconds", type=float, default=14400)
    args = parser.parse_args()
    cases = read_json(args.cases)["cases"]
    cases_by_name = {case["name"]: case for case in cases}
    cache = {c["name"]: c for c in read_json(args.old_cache)["cases"]}
    for case in cases:
        old = cache.get(case["name"], {})
        if old.get("request_sha256") != sha256_json(case["body"]) or old.get("old", {}).get("http_status") != 200:
            raise ValueError(f"successful matching old cache required: {case['name']}")
    fixture_groups = {index: [c["name"] for c in cases if c["name"].startswith(f"fixture:{index}:")]
                      for index in ("mercado", "wayfair", "mercado_local")}
    full_dependencies = {index for c in cases for index in c["body"]["index_names"].split(",")
                         if "payoneer" not in index}
    groups = {name: (names, {name}) for name, names in fixture_groups.items()}
    groups["all17"] = ([c["name"] for c in cases], full_dependencies)
    paths = restore_inputs(args.restore_state, args.restore_manifest)
    status = read_json(args.status) if args.status.exists() else {"started_at": now(), "groups": {}}
    status.update(reads_old_http=False, read_only=True, status="waiting", resumed_at=now(), pid=os.getpid(),
                  restore_inputs=[str(path) for path in paths],
                  restore_manifest=str(args.restore_manifest.resolve()) if args.restore_manifest else None)
    # A watcher restart reuses completed reports, including a report finalized
    # just before the watcher died. No completed group sends new requests again.
    for name, (names, _) in groups.items():
        report_path = args.report_dir / f"http_parity_after_root_restore_{name}_20261004.json"
        existing = completed_report(report_path, names, cases_by_name)
        if existing:
            status["groups"][name] = {"status": "complete", "report": str(report_path),
                                     "reused_completed_report": True, "summary": existing.get("summary")}
        elif name in status["groups"]:
            raise ValueError(f"previous group has no completed report: {name}")
    write_json(args.status, status)
    print(json.dumps({"pid": os.getpid(), "restore_inputs": status["restore_inputs"],
                      "reused_groups": sorted(status["groups"])}), flush=True)
    started = time.monotonic()
    while True:
        indices, statuses = aggregate_restore(paths)
        status["restore_statuses"] = statuses
        if "failed" in statuses.values():
            status.update(status="restore_failed", finished_at=now())
            write_json(args.status, status)
            return 2
        ready = {name for name, value in indices.items()
                 if value.get("complete") and value.get("counts_after")}
        for name, (names, dependencies) in groups.items():
            if name in status["groups"] or not dependencies <= ready:
                continue
            report = args.report_dir / f"http_parity_after_root_restore_{name}_20261004.json"
            status["groups"][name] = {"status": "running", "report": str(report), "started_at": now()}
            status["status"] = "testing"
            write_json(args.status, status)
            command = [sys.executable, str(Path(__file__).with_name("compare_legacy_search_http.py")),
                       "--cases", str(args.cases), "--reuse-old-report", str(args.old_cache),
                       "--require-old-cache", "--new-no-auth", "--report", str(report), "--names", *names]
            result = subprocess.run(command, check=False)
            entry = status["groups"][name]
            entry.update(status="complete" if result.returncode == 0 else "failed", returncode=result.returncode,
                         finished_at=now())
            if report.exists():
                entry["summary"] = read_json(report).get("summary")
            write_json(args.status, status)
            print(json.dumps({"group": name, **entry}), flush=True)
            if result.returncode:
                status.update(status="test_failed", finished_at=now())
                write_json(args.status, status)
                return result.returncode
        if "all17" in status["groups"]:
            status.update(status="complete", finished_at=now())
            write_json(args.status, status)
            return 0
        if time.monotonic() - started >= args.max_wait_seconds:
            status.update(status="timeout", finished_at=now())
            write_json(args.status, status)
            return 3
        status.update(status="waiting", waiting_for=sorted(full_dependencies - ready), last_checked_at=now())
        write_json(args.status, status)
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
