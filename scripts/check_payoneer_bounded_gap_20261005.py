#!/usr/bin/env python3
"""Read-only metadata comparison for a fixed Payoneer update-time range."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recheck_key5_live_metadata_20261005 import (FIELDS, active_target, base, doc_metadata,
                                               now, read_json, write_json)


def run(args):
    prior_raw = args.prior.read_bytes()
    prior = json.loads(prior_raw)
    old_bound = prior["indices"]["payoneer"]["source"]["aggregations"]["max_update_time"]
    new_bound = prior["indices"]["payoneer"]["target"]["aggregations"]["max_update_time"]
    if not prior["source_remote_verification"]["verified"] or not prior["target_config_unchanged_during_reads"]:
        raise RuntimeError("prior_live_configuration_binding_not_verified")
    config, binding = active_target()
    previous_binding = prior["target_config_binding"]
    if any(binding[key] != previous_binding[key] for key in ("reader_mainpid", "reader_config_sha256", "engine_config_sha256")):
        raise RuntimeError("active_target_changed_since_live_metadata")
    provider = prior["provider_by_index"]["payoneer"]
    source = base.Endpoint("legacy_es7", read_json(Path(prior["source_config"])))
    target = base.Endpoint(provider, config["providers"][provider])
    report = {"schema": "payoneer-bounded-live-metadata-gap-v1", "started_at_utc": now(),
        "status": "prepared", "read_only": True, "index": "payoneer", "target_provider": provider,
        "prior_report": str(args.prior), "prior_report_sha256": hashlib.sha256(prior_raw).hexdigest(),
        "prior_observation_utc": prior["finished_at_utc"], "source_verification_reused": prior["source_remote_verification"],
        "target_config_binding": binding, "fixed_range_field": "update_time",
        "range_start_exclusive_original_string": new_bound["value_as_string"],
        "range_end_inclusive_original_string": old_bound["value_as_string"],
        "source_fields_allowed": FIELDS, "page_limit": 500, "full_freshness_proven": False,
        "source_candidates": [], "comparisons": [], "requests": [],
        "limitations": ["One fixed date range based on the prior live observation, not a full change set.",
            "No scroll, PIT, pagination, source text or vectors. Reads are not an atomic cross-cluster snapshot.",
            "No-timestamp changes and hard deletes can be missed; cluster versions are reported independently.",
            "Earlier four-ID success remains in the prior report, which is not overwritten."]}
    write_json(args.report, report)
    if not args.execute:
        print(json.dumps({"status": "prepared", "network_requests": 0}))
        return 0
    payload = {"size": 100, "track_total_hits": True, "_source": FIELDS,
        "version": True, "seq_no_primary_term": True,
        "query": {"range": {"update_time": {"gt": new_bound["value_as_string"], "lte": old_bound["value_as_string"]}}},
        "sort": [{"update_time": {"order": "asc"}}]}
    for size in (100, 500):
        payload["size"] = size
        meta, body = source.request("POST", "/payoneer/_search", payload)
        report["requests"].append({"side": "source", "size": size, **meta})
        if body is None:
            report.update(status="source_failed_closed", finished_at_utc=now())
            write_json(args.report, report)
            return 2
        total_info = body.get("hits", {}).get("total")
        total = total_info.get("value") if isinstance(total_info, dict) else total_info
        relation = total_info.get("relation") if isinstance(total_info, dict) else "eq"
        shards = body.get("_shards", {})
        valid = (body.get("timed_out") is False and shards.get("failed") == 0
            and shards.get("successful") == shards.get("total") and relation == "eq" and isinstance(total, int))
        report.update(source_range_total=total, source_range_total_relation=relation)
        if not valid:
            report.update(status="source_partial_failed_closed", finished_at_utc=now())
            write_json(args.report, report)
            return 2
        if total > 500:
            report.update(status="partial_range_exceeds_500_no_target_reads", finished_at_utc=now(), bounded_range_fully_returned=False)
            write_json(args.report, report)
            return 3
        if total > size:
            continue
        hits = body.get("hits", {}).get("hits", [])
        if len(hits) != total or len({hit["_id"] for hit in hits}) != total:
            raise RuntimeError("source_single_page_count_or_duplicate_id")
        for hit in hits:
            source_fields = hit.get("_source", {})
            if set(source_fields) - set(FIELDS) or any(field not in source_fields for field in FIELDS):
                raise RuntimeError("source_metadata_field_scope_or_completeness_failed")
            report["source_candidates"].append({key: hit[key] for key in ("_id", "_index", "_version", "_seq_no", "_primary_term") if key in hit})
            report["source_candidates"][-1]["metadata"] = source_fields
        report["bounded_range_fully_returned"] = True
        break
    ids = [row["_id"] for row in report["source_candidates"]]
    if ids:
        new = doc_metadata(target, "payoneer", ids)
        report["target_mget"] = new
        report["requests"].append({"side": "target", "ids_count": len(ids), **new["request"]})
        if not new["complete"]:
            report.update(status="target_partial_failed_closed", finished_at_utc=now())
            write_json(args.report, report)
            return 2
        lookup = {row["_id"]: row for row in new["documents"]}
        for old in report["source_candidates"]:
            new = lookup[old["_id"]]
            differences = {}
            if new.get("found") is True:
                if any(field not in new["metadata"] for field in FIELDS):
                    raise RuntimeError("target_found_metadata_fields_incomplete")
                for field in FIELDS:
                    if old["metadata"][field] != new["metadata"][field]:
                        differences[field] = {"source": old["metadata"][field], "target": new["metadata"][field]}
            report["comparisons"].append({"id": old["_id"], "target_found": new.get("found"),
                "missing_in_target": new.get("found") is False, "metadata_equal": new.get("found") is True and not differences,
                "metadata_differences": differences})
    report.update(status="complete", finished_at_utc=now(),
        missing_ids=[row["id"] for row in report["comparisons"] if row["missing_in_target"]],
        metadata_difference_ids=[row["id"] for row in report["comparisons"] if row["metadata_differences"]],
        update_time_difference_ids=[row["id"] for row in report["comparisons"] if "update_time" in row["metadata_differences"]],
        del_flag_difference_ids=[row["id"] for row in report["comparisons"] if "del_flag" in row["metadata_differences"]])
    report["remaining_gap_confirmed"] = bool(report["missing_ids"] or report["metadata_difference_ids"])
    write_json(args.report, report)
    print(json.dumps({"report": str(args.report), **{key: report[key] for key in ("started_at_utc", "finished_at_utc", "source_range_total", "bounded_range_fully_returned", "missing_ids", "metadata_difference_ids", "update_time_difference_ids", "del_flag_difference_ids", "remaining_gap_confirmed")}}), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--prior", type=Path, default=Path("artifacts/key5_live_recheck_20261005.json"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/payoneer_bounded_freshness_gap_20261005.json"))
    args = parser.parse_args(); warnings.filterwarnings("ignore")
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
