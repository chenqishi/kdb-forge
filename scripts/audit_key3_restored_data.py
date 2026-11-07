#!/usr/bin/env python3
"""Audit 100 local snapshot records per key index against new logical ES names.

Default mode only prepares and validates local samples. --execute additionally
requires completed restore checkpoints, and reads only the new Serverless ES.
Reports contain hashes, IDs, counts and numeric errors, never source content.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from compare_es7_es8_online import compare_values
from compare_legacy_search_http import now, read_json, write_json
from migrate_es7_to_es8 import ESHttp
from retest_restored_http_cases import aggregate_restore, restore_inputs

ROOTS = ("title_embedding", "content_embedding")
SAMPLE_SIZE = 100
MAX_BATCH = 32
TOLERANCE = 1e-6
EXPECTED = {
    "mercado": {"docs": 22463, "title_embedding": 20966, "content_embedding": 21895},
    "wayfair": {"docs": 38923, "title_embedding": 35750, "content_embedding": 38882},
    "mercado_local": {"docs": 11435, "title_embedding": 9544, "content_embedding": 11327},
}


class AuditFailure(RuntimeError):
    """Sanitized failure codes only; response bodies are deliberately excluded."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def non_root(source: dict) -> dict:
    # Keep all nested vectors and every other field. Only the two explicitly
    # filtered root vectors are verified separately via indexed doc values.
    return {key: value for key, value in source.items() if key not in ROOTS}


def text_hashes(source: dict) -> dict:
    return {field: {"present": field in source, "sha256": digest(source.get(field))}
            for field in ("title", "content")}


def exact_difference_paths(left: Any, right: Any, path: str = "", limit: int = 30) -> list[str]:
    result = []
    if type(left) is not type(right):
        return [path or "<root>"]
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            child = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                result.append(child)
            else:
                result.extend(exact_difference_paths(left[key], right[key], child, limit - len(result)))
            if len(result) >= limit:
                break
    elif isinstance(left, list):
        if len(left) != len(right):
            result.append((path or "<root>") + ".length")
        for position, (a, b) in enumerate(zip(left, right)):
            result.extend(exact_difference_paths(a, b, f"{path}[{position}]", limit - len(result)))
            if len(result) >= limit:
                break
    elif left != right:
        result.append(path or "<root>")
    return result[:limit]


def absent_vector(value: Any) -> bool:
    return value is None or value == []


def valid_vector(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 1024
            and all(isinstance(item, (int, float)) and not isinstance(item, bool)
                    and math.isfinite(item) for item in value)
            and any(item != 0 for item in value))


def vector_summary(value: Any) -> dict:
    return {"present": not absent_vector(value), "dims": len(value) if isinstance(value, list) else 0,
            "valid": valid_vector(value), "sha256": digest(value)}


def check_vector(local: Any, indexed: Any) -> dict:
    result = {"local": vector_summary(local), "indexed": vector_summary(indexed)}
    if absent_vector(local) and absent_vector(indexed):
        result.update(passed=True, status="absent_in_both", max_abs_error=0.0)
    elif absent_vector(local):
        result.update(passed=False, status="unexpected_target_vector", max_abs_error=None)
    elif not valid_vector(local):
        result.update(passed=False, status="invalid_local_vector", max_abs_error=None)
    elif absent_vector(indexed):
        result.update(passed=False, status="missing_target_vector", max_abs_error=None)
    elif not valid_vector(indexed):
        result.update(passed=False, status="invalid_target_vector", max_abs_error=None)
    else:
        maximum = max(abs(float(a) - float(b)) for a, b in zip(local, indexed))
        result.update(passed=maximum <= TOLERANCE,
                      status="equal_within_tolerance" if maximum <= TOLERANCE else "numeric_mismatch",
                      max_abs_error=maximum)
    return result


class DigestReader:
    """Hash compressed bytes during the single forward gzip sampling pass."""
    def __init__(self, raw):
        self.raw = raw
        self.hash = hashlib.sha256()
        self.name = raw.name

    def read(self, size=-1):
        block = self.raw.read(size)
        self.hash.update(block)
        return block

    def tell(self):
        return self.raw.tell()


def uniform_positions(count: int, quota: int) -> set[int]:
    if quota < 0 or count < quota:
        raise AuditFailure("insufficient_base_records_for_sample")
    return {((2 * position + 1) * count) // (2 * quota) for position in range(quota)} if quota else set()


def sample_base(path: Path, expected_hash: str, count: int, quota: int,
                overrides: dict, updated_count: int) -> tuple[list, dict]:
    positions = uniform_positions(count, quota + updated_count)
    selected = []
    scanned = 0
    with path.open("rb") as raw:
        reader = DigestReader(raw)
        with gzip.GzipFile(fileobj=reader, mode="rb") as handle:
            for line in handle:
                if not line.strip():
                    continue
                position = scanned
                scanned += 1
                if position not in positions:
                    continue
                record = json.loads(line)
                if not isinstance(record.get("_source"), dict) or "_id" not in record:
                    raise AuditFailure("invalid_selected_base_record")
                if str(record["_id"]) not in overrides:
                    selected.append({"record": record, "origin": "base", "base_position": position})
        actual_hash = reader.hash.hexdigest()
    if actual_hash != expected_hash:
        raise AuditFailure("base_compressed_sha_mismatch")
    if scanned != count:
        raise AuditFailure("base_record_count_mismatch")
    if len(selected) < quota:
        raise AuditFailure("insufficient_distinct_base_samples")
    return selected[:quota], {"compressed_sha256": actual_hash, "records_scanned": scanned,
                              "uniform_candidate_positions": sorted(positions)}


def load_delta(manifest_path: Path, import_path: Path, indices: list[str]) -> tuple[dict, dict]:
    manifest, imported = read_json(manifest_path), read_json(import_path)
    if (not manifest.get("ready_for_import") or not imported.get("all_pass")
            or Path(imported.get("manifest", "")).resolve() != manifest_path.resolve()):
        raise AuditFailure("incremental_import_not_verified")
    imported_rows = {row["source_index"]: row for row in imported["indices"]}
    output = {name: {} for name in indices}
    details = {name: {"records": 0, "new_count": 0, "updated_count": 0} for name in indices}
    for row in manifest["indices"]:
        name = row["source_index"]
        if name not in output:
            continue
        verified = imported_rows.get(name, {})
        if verified.get("status") != "done" or verified.get("all_delta_docs_equal") is not True:
            raise AuditFailure("selected_delta_import_not_verified")
        info = row["delta_dump"]
        path = Path(info["file"])
        if file_sha(path) != info["sha256"]:
            raise AuditFailure("delta_compressed_sha_mismatch")
        with gzip.open(path, "rb") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        if len(records) != info["records"] or len({str(record["_id"]) for record in records}) != len(records):
            raise AuditFailure("delta_count_or_duplicate_id")
        if len(records) != row["new_count"] + row["updated_count"]:
            raise AuditFailure("delta_classification_count_mismatch")
        output[name] = {str(record["_id"]): record for record in records}
        details[name] = {"records": len(records), "new_count": row["new_count"],
                         "updated_count": row["updated_count"], "compressed_sha256": info["sha256"]}
    return output, {"manifest_sha256": file_sha(manifest_path), "import_report_sha256": file_sha(import_path),
                    "verified": True, "indices": details}


def prepare_local(args) -> tuple[dict, dict]:
    states = {state["source_index"]: state for path in (args.dump_dir / "states").glob("*.json")
              if (state := read_json(path)).get("source_index") in args.indices}
    if set(states) != set(args.indices):
        raise AuditFailure("missing_selected_base_checkpoint")
    overrides, delta_info = load_delta(args.incremental_manifest, args.incremental_report, args.indices)
    samples = {}
    local_info = {"incremental": delta_info, "indices": {}}
    for name in args.indices:
        state, delta = states[name], overrides[name]
        details = delta_info["indices"][name]
        if len(delta) > SAMPLE_SIZE:
            raise AuditFailure("delta_records_exceed_sample_size")
        count = int(state["docs_exported"])
        if count + details["new_count"] != EXPECTED[name]["docs"]:
            raise AuditFailure("local_merged_count_differs_from_expected")
        selected, scan_info = sample_base(Path(state["file"]), state["sha256"], count,
                                          SAMPLE_SIZE - len(delta), delta, details["updated_count"])
        selected.extend({"record": delta[ident], "origin": "verified_delta", "base_position": None}
                        for ident in sorted(delta))
        if len(selected) != SAMPLE_SIZE or len({str(s["record"]["_id"]) for s in selected}) != SAMPLE_SIZE:
            raise AuditFailure("sample_count_or_duplicate_id")
        samples[name] = selected
        local_info["indices"][name] = {**scan_info, "expected_counts": EXPECTED[name],
                                       "samples": SAMPLE_SIZE, "base_samples": SAMPLE_SIZE - len(delta),
                                       "verified_delta_samples": len(delta),
                                       "sample_root_distribution": {field: {
                                           "valid": sum(valid_vector(s["record"]["_source"].get(field)) for s in selected),
                                           "absent": sum(absent_vector(s["record"]["_source"].get(field)) for s in selected),
                                           "invalid": sum(not absent_vector(s["record"]["_source"].get(field))
                                                          and not valid_vector(s["record"]["_source"].get(field))
                                                          for s in selected)} for field in ROOTS}}
        print(json.dumps({"prepared_index": name, "samples": SAMPLE_SIZE,
                          "verified_delta_samples": len(delta), "base_records_scanned": count}), flush=True)
    return samples, local_info


class NewTarget:
    def __init__(self, config):
        self.client = ESHttp(config, timeout=120)

    def call(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except Exception as exc:
            raise AuditFailure(f"target_transport_{type(exc).__name__}") from None
        if not response.ok:
            raise AuditFailure(f"target_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise AuditFailure("target_non_json_response") from None
        if body.get("timed_out") or (body.get("_shards") or {}).get("failed", 0):
            raise AuditFailure("target_partial_response")
        return body

    def mapping(self, name):
        body = self.call("GET", f"/{name}/_mapping")
        if set(body) != {name}:
            raise AuditFailure("logical_name_is_not_exact_physical_index")
        mapping = body[name]["mappings"]
        roots = {field: {key: mapping.get("properties", {}).get(field, {}).get(key)
                         for key in ("type", "dims", "index")} for field in ROOTS}
        return {"source_projection": mapping.get("_source", {}), "root_mappings": roots,
                "root_mapping_pass": all(value == {"type": "dense_vector", "dims": 1024, "index": True}
                                         for value in roots.values()),
                "source_enabled": mapping.get("_source", {}).get("enabled", True)}

    def counts(self, name):
        body = self.call("POST", f"/{name}/_search", json={"size": 0, "track_total_hits": True,
                         "aggs": {field: {"filter": {"exists": {"field": field}}} for field in ROOTS}})
        total = body["hits"]["total"]
        if isinstance(total, dict) and total.get("relation") != "eq":
            raise AuditFailure("count_not_exact")
        return {"docs": total["value"] if isinstance(total, dict) else total,
                **{field: body["aggregations"][field]["doc_count"] for field in ROOTS}}

    def read(self, name, ids):
        if not 0 < len(ids) <= MAX_BATCH:
            raise AuditFailure("invalid_read_batch_size")
        body = self.call("POST", f"/{name}/_mget", json={"ids": ids})
        rows = body.get("docs", [])
        if len(rows) != len(ids) or any(row.get("error") for row in rows):
            raise AuditFailure("mget_partial_response")
        if {str(row["_id"]) for row in rows} != set(ids) or any(row["_index"] != name for row in rows):
            raise AuditFailure("mget_identity_mismatch")
        docs = {str(row["_id"]): row for row in rows}
        found = [ident for ident in ids if docs[ident].get("found")]
        hits = []
        if found:
            indexed = self.call("POST", f"/{name}/_search", json={"size": len(found), "_source": False,
                                "query": {"ids": {"values": found}}, "docvalue_fields": list(ROOTS)})
            hits = indexed.get("hits", {}).get("hits", [])
            if ({str(hit["_id"]) for hit in hits} != set(found)
                    or any(hit.get("_index") != name for hit in hits)):
                raise AuditFailure("indexed_vector_read_not_complete")
        vectors = {}
        for hit in hits:
            fields = {}
            for field in ROOTS:
                value = (hit.get("fields") or {}).get(field)
                if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
                    value = value[0]
                fields[field] = value
            vectors[str(hit["_id"])] = fields
        return docs, vectors


def document_check(sample, current, indexed):
    record = sample["record"]
    local = record["_source"]
    result = {"id": str(record["_id"]), "origin": sample["origin"], "base_position": sample["base_position"],
              "found": bool(current and current.get("found"))}
    if not result["found"]:
        return {**result, "passed": False, "status": "missing_target_document"}
    new = current.get("_source")
    if not isinstance(new, dict):
        return {**result, "passed": False, "status": "target_source_unavailable"}
    a, b = non_root(local), non_root(new)
    structural_paths = []
    structural_equal, numeric_diff = compare_values(a, b, mismatches=structural_paths)
    source_equal = digest(a) == digest(b)
    result["non_root_source"] = {"local_sha256": digest(a), "target_sha256": digest(b),
                                  "canonical_hash_equal": source_equal,
                                  "mismatch_paths": [] if source_equal else exact_difference_paths(a, b),
                                  "structural_equal_with_tolerance": structural_equal,
                                  "max_numeric_error": numeric_diff}
    result["text_fields"] = {"local": text_hashes(local), "target": text_hashes(new),
                              "hashes_equal": text_hashes(local) == text_hashes(new)}
    result["root_vectors"] = {field: check_vector(local.get(field), indexed.get(field)) for field in ROOTS}
    result["root_source_presence"] = {field: field in new for field in ROOTS}
    result["passed"] = (source_equal and result["text_fields"]["hashes_equal"]
                        and all(check["passed"] for check in result["root_vectors"].values()))
    result["status"] = "equal" if result["passed"] else "data_mismatch"
    return result


def audit_index(target, name, samples, report, path):
    mapping = target.mapping(name)
    counts = target.counts(name)
    entry = {"mapping": mapping, "expected_counts": EXPECTED[name], "target_counts": counts,
             "counts_equal": counts == EXPECTED[name], "documents": []}
    report["indices"][name] = entry
    write_json(path, report)
    for start in range(0, len(samples), MAX_BATCH):
        batch = samples[start:start + MAX_BATCH]
        docs, vectors = target.read(name, [str(sample["record"]["_id"]) for sample in batch])
        entry["documents"].extend(document_check(sample, docs.get(str(sample["record"]["_id"])),
                                                 vectors.get(str(sample["record"]["_id"]), {})) for sample in batch)
        write_json(path, report)
    entry["passed"] = (entry["counts_equal"] and mapping["root_mapping_pass"] and mapping["source_enabled"]
                       and len(entry["documents"]) == SAMPLE_SIZE and all(row["passed"] for row in entry["documents"]))
    entry["sample_passed"] = sum(row["passed"] for row in entry["documents"])
    entry["root_max_abs_error"] = {field: max((row.get("root_vectors", {}).get(field, {}).get("max_abs_error") or 0
                                               for row in entry["documents"]), default=0) for field in ROOTS}
    entry["root_sample_status_counts"] = {field: {status: sum(row.get("root_vectors", {}).get(field, {}).get("status") == status
                                                        for row in entry["documents"])
                                                   for status in sorted({row.get("root_vectors", {}).get(field, {}).get("status", "not_checked")
                                                                         for row in entry["documents"]})}
                                          for field in ROOTS}
    entry["finished_at"] = now()
    write_json(path, report)
    return entry


def run(args):
    report = {"started_at": now(), "mode": "execute" if args.execute else "dry_run", "read_only": True,
              "reads_old_es": False, "max_batch_size": MAX_BATCH, "sample_size_per_index": SAMPLE_SIZE,
              "root_error_tolerance": TOLERANCE, "indices": {}, "status": "preparing"}
    write_json(args.report, report)
    try:
        if args.execute:
            paths = restore_inputs(None, args.restore_manifest)
            indices, statuses = aggregate_restore(paths)
            if "failed" in statuses.values() or any(not indices.get(name, {}).get("complete")
                    or not indices[name].get("counts_after") for name in args.indices):
                raise AuditFailure("selected_restore_not_complete")
            report["restore_inputs"] = [str(path) for path in paths]
        samples, local_info = prepare_local(args)
        report["local_inputs"] = local_info
        if not args.execute:
            for name, selected in samples.items():
                report["indices"][name] = {"samples": [{"id": str(s["record"]["_id"]), "origin": s["origin"],
                    "base_position": s["base_position"], "non_root_sha256": digest(non_root(s["record"]["_source"])),
                    "text_fields": text_hashes(s["record"]["_source"]),
                    "root_vectors": {field: vector_summary(s["record"]["_source"].get(field)) for field in ROOTS}}
                    for s in selected]}
            report.update(status="prepared", finished_at=now(), es_requests=0)
            write_json(args.report, report)
            return 0
        config = read_json(args.target_config)
        if str(config.get("es_version")) != "8.17":
            raise AuditFailure("target_config_not_es817")
        endpoint = config["providers"]["serverless"]
        report["target"] = {"provider": "serverless", "es_version": "8.17",
                             "endpoint_sha256": digest(endpoint.get("hosts") or endpoint.get("host"))}
        target = NewTarget(endpoint)
        report["status"] = "checking"
        for name in args.indices:
            entry = audit_index(target, name, samples[name], report, args.report)
            print(json.dumps({"checked_index": name, "sample_passed": entry["sample_passed"],
                              "samples": SAMPLE_SIZE, "counts_equal": entry["counts_equal"],
                              "passed": entry["passed"]}), flush=True)
        report.update(status="complete", finished_at=now(),
                      all_pass=all(entry["passed"] for entry in report["indices"].values()))
        write_json(args.report, report)
        return 0 if report["all_pass"] else 2
    except Exception as exc:
        report.update(status="failed", error=str(exc) if isinstance(exc, AuditFailure) else type(exc).__name__,
                      failed_at=now())
        write_json(args.report, report)
        print(json.dumps({"status": "failed", "error": report["error"]}), flush=True)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="read new ES only after completed restore gate")
    parser.add_argument("--indices", nargs="+", choices=list(EXPECTED), default=list(EXPECTED))
    parser.add_argument("--dump-dir", type=Path, default=Path("migration_runs/local_dump_20261001/data"))
    parser.add_argument("--incremental-manifest", type=Path, default=Path("migration_runs/incremental_local_20261002T161500Z/manifest.json"))
    parser.add_argument("--incremental-report", type=Path, default=Path("migration_runs/incremental_local_20261002T161500Z/import_report.json"))
    parser.add_argument("--restore-manifest", type=Path, default=Path("artifacts/root_restore_partition_manifest_20261004.json"))
    parser.add_argument("--target-config", type=Path, default=Path("config/config_es_runtime.local.json"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if len(set(args.indices)) != len(args.indices):
        parser.error("duplicate indices")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
