#!/usr/bin/env python3
"""Prepare merged local root counts, then optionally compare completed new ES.

Default mode performs no network requests. Invalid explicit root values are
recorded separately from missing, null and empty arrays. --check-new requires
all 81 indices restored with the same verified local inputs and live endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_legacy_search_http import now, read_json, write_json
from restore_local_root_vectors import (ROOTS, SafeFailure, Target, digest, file_sha,
                                        load_inputs, merged_records, text_signature, valid_vector)

REQUIRED_TOTALS = {"docs": 124634, "title_embedding": 115726, "content_embedding": 123482}
CATEGORIES = ("valid", "missing", "null", "empty_list", "invalid")


class CountFailure(RuntimeError):
    pass


def invalid_value_sha(value):
    # Nonfinite source values must be reportable too. Only their hash is saved;
    # the NaN/Infinity serialization used to hash them never enters the report.
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=True).encode()).hexdigest()


def classify_root(source, field):
    if field not in source:
        return "missing", None
    value = source[field]
    if value is None:
        return "null", None
    if isinstance(value, list) and not value:
        return "empty_list", None
    try:
        if valid_vector(value):
            return "valid", None
    except (OverflowError, ValueError):
        pass
    if not isinstance(value, list):
        reason = "wrong_type"
    elif len(value) != 1024:
        reason = "wrong_dimensions"
    elif any(not isinstance(item, (int, float)) or isinstance(item, bool) for item in value):
        reason = "nonnumeric_component"
    else:
        try:
            reason = "nonfinite_component" if any(not math.isfinite(item) for item in value) else "all_zero"
        except OverflowError:
            reason = "numeric_overflow"
    return "invalid", reason


def empty_entry(base, delta_count):
    return {"complete": False, "counts": {"docs": 0, **{field: 0 for field in ROOTS}},
            "root_categories": {field: {category: 0 for category in CATEGORIES} for field in ROOTS},
            "invalid_roots": [], "base_compressed_sha256": base["sha256"],
            "base_records": int(base["docs_exported"]), "verified_delta_records": delta_count}


def add_record(entry, record):
    entry["counts"]["docs"] += 1
    source = record["_source"]
    for field in ROOTS:
        category, reason = classify_root(source, field)
        entry["root_categories"][field][category] += 1
        if category == "valid":
            entry["counts"][field] += 1
        elif category == "invalid":
            value = source[field]
            entry["invalid_roots"].append({"id": str(record["_id"]), "field": field, "reason": reason,
                                          "value_type": type(value).__name__,
                                          "dims": len(value) if isinstance(value, list) else None,
                                          "value_sha256": invalid_value_sha(value),
                                          "text_signature": text_signature(source)})


def totals(indices):
    return {key: sum(entry["counts"][key] for entry in indices.values()) for key in REQUIRED_TOTALS}


def content_hash(expected):
    return digest({"input_sha256": expected["input_sha256"], "indices": expected["indices"],
                   "totals": expected["totals"], "required_totals": expected["required_totals"],
                   "invalid_root_counts": expected["invalid_root_counts"],
                   "input_vector_quality_pass": expected["input_vector_quality_pass"],
                   "totals_match_required": expected["totals_match_required"]})


def entry_hash(entry):
    return digest({key: value for key, value in entry.items() if key != "entry_sha256"})


def validate_entry(entry):
    if entry.get("entry_sha256") != entry_hash(entry):
        raise CountFailure("completed_index_entry_sha_mismatch")
    count = entry["counts"]["docs"]
    for field in ROOTS:
        categories = entry["root_categories"][field]
        if (set(categories) != set(CATEGORIES) or sum(categories.values()) != count
                or categories["valid"] != entry["counts"][field]):
            raise CountFailure("completed_index_root_category_inconsistency")
    if sum(categories["invalid"] for categories in entry["root_categories"].values()) != len(entry["invalid_roots"]):
        raise CountFailure("completed_index_invalid_details_inconsistency")


def verified_inputs(args, progress):
    names, selected, baseline, overrides, identity = load_inputs(args)
    if len(names) != 81 or set(selected) != set(names):
        raise CountFailure("expected_exact_81_serverless_scope")
    for position, name in enumerate(names):
        path = Path(baseline[name]["file"])
        if path.resolve() != Path(selected[name]["dump_file"]).resolve():
            raise CountFailure("selected_dump_path_differs_from_base_checkpoint")
        progress.update(status="verifying_local_files", current_index=name, files_verified=position,
                        last_updated_at=now())
        write_json(args.progress, progress)
        if file_sha(path) != baseline[name]["sha256"]:
            raise CountFailure("actual_base_compressed_sha_mismatch")
    progress.update(files_verified=len(names), current_index=None, last_updated_at=now())
    write_json(args.progress, progress)
    return names, selected, baseline, overrides, identity


def prepare_expected(args, inputs, progress):
    names, _, baseline, overrides, identity = inputs
    input_hash = digest(identity)
    if args.expected.exists():
        if not args.resume:
            raise CountFailure("expected_artifact_exists_use_resume")
        expected = read_json(args.expected)
        if expected.get("input_sha256") != input_hash or expected.get("input_identity") != identity:
            raise CountFailure("expected_artifact_inputs_changed")
        if set(expected.get("indices", {})) - set(names):
            raise CountFailure("expected_artifact_scope_changed")
        if expected.get("status") == "complete":
            validate_expected(expected, names, identity)
            progress.update(status="complete", current_index=None, completed_indices=81,
                            totals=expected["totals"], totals_match_required=expected["totals_match_required"],
                            invalid_root_counts=expected["invalid_root_counts"], reused_completed_artifact=True,
                            finished_at=now())
            write_json(args.progress, progress)
            return expected
        if expected.get("status") != "preparing":
            raise CountFailure("unexpected_expected_artifact_status")
        for entry in expected["indices"].values():
            if entry.get("complete"):
                validate_entry(entry)
    else:
        expected = {"started_at": now(), "status": "preparing", "reads_es": False, "reads_old_es": False,
                    "scope": names, "input_identity": identity, "input_sha256": input_hash,
                    "required_totals": REQUIRED_TOTALS, "indices": {}}
    last_saved = time.monotonic()
    for name in names:
        if expected["indices"].get(name, {}).get("complete"):
            continue
        entry = empty_entry(baseline[name], len(overrides[name]))
        expected["indices"][name] = entry
        progress.update(status="counting_local_merged_records", current_index=name,
                        current_counts=entry["counts"].copy(), last_updated_at=now())
        write_json(args.progress, progress)
        for record in merged_records(Path(baseline[name]["file"]), overrides[name]):
            add_record(entry, record)
            if time.monotonic() - last_saved >= 10:
                expected["totals_so_far"] = totals(expected["indices"])
                write_json(args.expected, expected)
                progress.update(current_counts=entry["counts"].copy(),
                                current_invalid_roots=len(entry["invalid_roots"]),
                                completed_indices=sum(row["complete"] for row in expected["indices"].values()),
                                totals_so_far=expected["totals_so_far"], last_updated_at=now())
                write_json(args.progress, progress)
                last_saved = time.monotonic()
        if entry["counts"]["docs"] < entry["base_records"]:
            raise CountFailure("merged_docs_below_base_count")
        if any(sum(categories.values()) != entry["counts"]["docs"] for categories in entry["root_categories"].values()):
            raise CountFailure("root_category_count_does_not_cover_all_documents")
        entry.update(complete=True, finished_at=now())
        entry["entry_sha256"] = entry_hash(entry)
        expected["totals_so_far"] = totals(expected["indices"])
        write_json(args.expected, expected)
        progress.update(completed_indices=sum(row["complete"] for row in expected["indices"].values()),
                        totals_so_far=expected["totals_so_far"], current_counts=entry["counts"].copy(),
                        current_invalid_roots=len(entry["invalid_roots"]), last_updated_at=now())
        write_json(args.progress, progress)
        print(json.dumps({"prepared_index": name, "counts": entry["counts"],
                          "invalid_roots": len(entry["invalid_roots"]),
                          "completed_indices": progress["completed_indices"]}), flush=True)
    expected.update(status="complete", totals=totals(expected["indices"]), finished_at=now())
    expected["totals_match_required"] = expected["totals"] == REQUIRED_TOTALS
    expected["invalid_root_counts"] = {field: sum(entry["root_categories"][field]["invalid"]
                                                 for entry in expected["indices"].values()) for field in ROOTS}
    expected["input_vector_quality_pass"] = not any(expected["invalid_root_counts"].values())
    expected["content_sha256"] = content_hash(expected)
    write_json(args.expected, expected)
    progress.update(status="complete", current_index=None, completed_indices=81,
                    totals=expected["totals"], totals_match_required=expected["totals_match_required"],
                    invalid_root_counts=expected["invalid_root_counts"], finished_at=now())
    write_json(args.progress, progress)
    return expected


def validate_expected(expected, names, identity):
    if (expected.get("status") != "complete" or set(expected.get("indices", {})) != set(names)
            or expected.get("scope") != names or not all(row.get("complete") for row in expected["indices"].values())):
        raise CountFailure("expected_artifact_not_complete_81")
    if expected.get("input_sha256") != digest(identity) or expected.get("input_identity") != identity:
        raise CountFailure("expected_artifact_inputs_changed")
    for entry in expected["indices"].values():
        validate_entry(entry)
    derived_invalid = {field: sum(entry["root_categories"][field]["invalid"]
                                   for entry in expected["indices"].values()) for field in ROOTS}
    if (expected.get("invalid_root_counts") != derived_invalid
            or expected.get("input_vector_quality_pass") is not (not any(derived_invalid.values()))):
        raise CountFailure("expected_invalid_root_summary_inconsistency")
    if expected.get("totals") != totals(expected["indices"]):
        raise CountFailure("expected_totals_do_not_match_index_sums")
    if expected.get("content_sha256") != content_hash(expected):
        raise CountFailure("expected_artifact_content_sha_mismatch")
    if expected.get("totals") != REQUIRED_TOTALS or expected.get("required_totals") != REQUIRED_TOTALS:
        raise CountFailure("local_totals_differ_from_required")


def restore_gate(manifest_path, names, baseline, identity, endpoint):
    manifest = read_json(manifest_path)
    groups = manifest["groups"]
    members = [name for group in groups.values() for name in group["indices"]]
    if len(members) != 81 or len(set(members)) != 81 or set(members) != set(names):
        raise CountFailure("restore_manifest_not_exact_81_scope")
    checked = {}
    for group in groups.values():
        state = read_json(Path(group["state"]))
        if state.get("apply") is not True or state.get("status") in {"failed", "partitioned"}:
            raise CountFailure("restore_checkpoint_not_applied_or_failed")
        subset = sorted(group["indices"], key=lambda name: ({"mercado": 0, "wayfair": 1, "mercado_local": 2}.get(name, 3), name))
        job = {"names": subset, "baseline_sha": {name: baseline[name]["sha256"] for name in subset},
               "incremental_manifest_sha": identity["incremental_manifest_sha"],
               "incremental_report_sha": identity["incremental_report_sha"],
               "endpoint_sha256": digest(endpoint.get("hosts") or endpoint.get("host")), "apply": True}
        if state.get("job_sha256") != digest(job):
            raise CountFailure("restore_checkpoint_input_or_endpoint_mismatch")
        if set(state.get("indices", {})) != set(subset):
            raise CountFailure("restore_partition_has_incomplete_or_extra_index_scope")
        for name in subset:
            progress = state["indices"][name]
            if not progress.get("complete") or not progress.get("counts_after"):
                raise CountFailure("all81_restore_not_complete")
            if progress.get("skips"):
                raise CountFailure("restore_contains_unresolved_skips")
            checked[name] = {"complete": True, "counts_after": progress["counts_after"]}
    return checked


def check_new(args, inputs, progress):
    names, _, baseline, _, identity = inputs
    expected = read_json(args.expected)
    validate_expected(expected, names, identity)
    config = read_json(args.target_config)
    if str(config.get("es_version")) != "8.17":
        raise CountFailure("target_config_not_es817")
    endpoint = config["providers"]["serverless"]
    gate = restore_gate(args.restore_manifest, names, baseline, identity, endpoint)
    report = {"started_at": now(), "read_only": True, "reads_old_es": False, "target_provider": "serverless",
              "expected_artifact": str(args.expected), "expected_sha256": expected["content_sha256"],
              "endpoint_sha256": digest(endpoint.get("hosts") or endpoint.get("host")),
              "restored_indices": len(gate), "indices": {}, "status": "checking"}
    write_json(args.report, report)
    target = Target(endpoint)
    for name in names:
        actual = target.counts(name)
        wanted = expected["indices"][name]["counts"]
        report["indices"][name] = {"expected": wanted, "target": actual, "equal": actual == wanted,
                                   "checkpoint_counts_after": gate[name]["counts_after"],
                                   "checkpoint_count_equal": gate[name]["counts_after"] == wanted}
        write_json(args.report, report)
        progress.update(status="checking_new_counts", current_index=name,
                        checked_indices=len(report["indices"]), last_updated_at=now())
        write_json(args.progress, progress)
        print(json.dumps({"checked_index": name, **report["indices"][name]}), flush=True)
    report["expected_totals"] = expected["totals"]
    report["target_totals"] = {key: sum(entry["target"][key] for entry in report["indices"].values()) for key in REQUIRED_TOTALS}
    report["count_parity_pass"] = (report["target_totals"] == expected["totals"]
                                   and all(entry["equal"] and entry["checkpoint_count_equal"] for entry in report["indices"].values()))
    report["input_vector_quality_pass"] = expected["input_vector_quality_pass"]
    report["source_invalid_root_counts"] = expected["invalid_root_counts"]
    report.update(status="complete", finished_at=now(),
                  all_pass=report["count_parity_pass"] and report["input_vector_quality_pass"])
    write_json(args.report, report)
    progress.update(status="complete", current_index=None, checked_indices=81,
                    target_totals=report["target_totals"], all_pass=report["all_pass"], finished_at=now())
    write_json(args.progress, progress)
    return 0 if report["all_pass"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-new", action="store_true", help="read new counts only after all81 restore gate")
    parser.add_argument("--resume", action="store_true", help="reuse completed local index scans after actual input hash verification")
    parser.add_argument("--dump-dir", default="migration_runs/local_dump_20261001/data")
    parser.add_argument("--shard-plan", default="migration_runs/local_dump_20261001/data/shard_plan_1g.json")
    parser.add_argument("--incremental-manifest", default="migration_runs/incremental_local_20261002T161500Z/manifest.json")
    parser.add_argument("--incremental-report", default="migration_runs/incremental_local_20261002T161500Z/import_report.json")
    parser.add_argument("--expected", type=Path, default=Path("artifacts/all81_expected_root_counts_20261004.json"))
    parser.add_argument("--progress", type=Path, default=Path("artifacts/all81_expected_root_counts_progress_20261004.json"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/all81_target_root_counts_20261004.json"))
    parser.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    parser.add_argument("--target-config", type=Path, default=Path("config/config_es_runtime.local.json"))
    args = parser.parse_args()
    args.indices = None  # load_inputs derives exactly all selected Serverless names.
    progress = {"started_at": now(), "pid": os.getpid(), "reads_old_es": False,
                "mode": "check_new" if args.check_new else "local_only", "status": "starting"}
    write_json(args.progress, progress)
    try:
        inputs = verified_inputs(args, progress)
        if args.check_new:
            return check_new(args, inputs, progress)
        expected = prepare_expected(args, inputs, progress)
        print(json.dumps({"expected_artifact": str(args.expected), "totals": expected["totals"],
                          "totals_match_required": expected["totals_match_required"],
                          "invalid_root_counts": expected["invalid_root_counts"], "es_requests": 0}), flush=True)
        return 0 if expected["totals_match_required"] and expected["input_vector_quality_pass"] else 2
    except Exception as exc:
        code = str(exc) if isinstance(exc, (CountFailure, SafeFailure)) else type(exc).__name__
        progress.update(status="failed", error=code, failed_at=now())
        write_json(args.progress, progress)
        print(json.dumps({"status": "failed", "error": code}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
