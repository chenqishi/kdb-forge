#!/usr/bin/env python3
"""Restore missing root vectors from local backups to selected ES8 Serverless names.

Only --apply enables mutations. Never reads ES7, creates indices, generates
embeddings, or upserts missing documents. Checkpoints contain no document text
or vectors. A partially acknowledged batch never advances the input offset.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_es7_to_es8 import ESHttp

# ujson is optional. The temporary dependency directory on this host also
# contains an incompatible orjson wheel, so never auto-import that wheel.
try:
    import ujson
    decode = ujson.loads
except ImportError:
    decode = json.loads

ROOTS = ("title_embedding", "content_embedding")
TEXTS = ("title", "content")
MAX_DOCS = 32
MAX_BYTES = 2 * 1024 * 1024
BAD_SKIPS = {"missing_id", "content_changed", "version_not_visible", "invalid_current_vector"}


class SafeFailure(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def valid_vector(value):
    return (isinstance(value, list) and len(value) == 1024
            and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                    and math.isfinite(x) for x in value)
            and any(x != 0 for x in value))


def equal_vectors(left, right):
    return (valid_vector(left) and valid_vector(right)
            and all(abs(float(a) - float(b)) <= 1e-6 for a, b in zip(left, right)))


def text_signature(source):
    # Distinguish a missing field from explicit null; never retain text in logs.
    return {key: {"present": key in source, "sha256": digest(source.get(key))}
            for key in TEXTS}


def version(hit):
    if not isinstance(hit, dict):
        return None
    seq, term = hit.get("_seq_no"), hit.get("_primary_term")
    return (seq, term) if isinstance(seq, int) and isinstance(term, int) else None


def field_vector(hit, key):
    value = (hit.get("fields") or {}).get(key)
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    return value


class Target:
    def __init__(self, config):
        self.client = ESHttp(config, timeout=120)

    def call(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except Exception as exc:
            raise SafeFailure(f"target_transport_{type(exc).__name__}") from None
        if not response.ok:
            # ES error bodies can include original documents, so never emit them.
            raise SafeFailure(f"target_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise SafeFailure("target_non_json_response") from None
        if body.get("timed_out") or (body.get("_shards") or {}).get("failed", 0):
            raise SafeFailure("target_partial_response")
        return body

    def read(self, index, ids):
        got = self.call("POST", f"/{index}/_mget", json={
            "docs": [{"_id": ident, "_source": list(TEXTS + ROOTS)} for ident in ids],
        })
        if len(got.get("docs", [])) != len(ids) or any(d.get("error") for d in got.get("docs", [])):
            raise SafeFailure("mget_partial_response")
        docs = {str(d["_id"]): d for d in got["docs"]}
        found = [ident for ident in ids if docs[ident].get("found")]
        hits = []
        if found:
            body = self.call("POST", f"/{index}/_search", json={
                "size": len(found), "_source": False, "seq_no_primary_term": True,
                "query": {"ids": {"values": found}}, "docvalue_fields": list(ROOTS),
            })
            hits = body.get("hits", {}).get("hits", [])
        return docs, {str(h["_id"]): h for h in hits}

    def counts(self, index):
        aggs = {field: {"filter": {"exists": {"field": field}}} for field in ROOTS}
        body = self.call("POST", f"/{index}/_search", json={
            "size": 0, "track_total_hits": True, "aggs": aggs,
        })
        total = body["hits"]["total"]
        return {"docs": total["value"] if isinstance(total, dict) else total,
                **{field: body["aggregations"][field]["doc_count"] for field in ROOTS}}

    def preflight(self, index):
        body = self.call("GET", f"/{index}/_mapping")
        if set(body) != {index}:
            raise SafeFailure("logical_name_is_not_the_exact_physical_index")
        mapping = body[index]["mappings"]
        for field in ROOTS:
            prop = mapping.get("properties", {}).get(field, {})
            if prop.get("type") != "dense_vector" or prop.get("dims") != 1024 or prop.get("index") is not True:
                raise SafeFailure("root_vector_mapping_not_supported")
        if mapping.get("_source", {}).get("enabled") is False:
            raise SafeFailure("source_disabled")
        source_mapping = mapping.get("_source", {})
        excluded = source_mapping.get("excludes", [])
        if source_mapping.get("includes") or set(excluded) - set(ROOTS):
            # Partial updates also rebuild indexed fields from stored _source.
            # We can only protect exclusions for the roots reconstructed here.
            raise SafeFailure("source_filters_exclude_fields_other_than_roots")
        return {"source_excludes": excluded}


def decide(record, current, indexed):
    ident = str(record["_id"])
    if not current or not current.get("found"):
        return None, "missing_id"
    if version(current) is None or version(current) != version(indexed):
        return None, "version_not_visible"
    source = current.get("_source")
    if not isinstance(source, dict) or text_signature(source) != text_signature(record["_source"]):
        return None, "content_changed"
    patch, added = {}, []
    for field in ROOTS:
        existing = field_vector(indexed, field)
        if existing is not None and not valid_vector(existing):
            return None, "invalid_current_vector"
        # Preserve EVERY existing root vector in the same CAS update. Otherwise
        # filtered _source would erase the other root during partial updates.
        if existing is not None:
            patch[field] = existing
        elif source.get(field) is not None:
            return None, "invalid_current_vector"
        elif valid_vector(record["_source"].get(field)):
            patch[field] = record["_source"][field]
            added.append(field)
    if not added:
        return None, "already_present_or_no_backup_vector"
    return {"_id": ident, "version": version(current), "doc": patch,
            "added": added, "text_signature": text_signature(source)}, None


def bulk_parts(index, updates):
    pending, payload = [], bytearray()
    for update in updates:
        seq, term = update["version"]
        pair = encoded({"update": {"_index": index, "_id": update["_id"],
                                   "if_seq_no": seq, "if_primary_term": term}}) + b"\n"
        pair += encoded({"doc": update["doc"]}) + b"\n"
        if len(pair) > MAX_BYTES:
            raise SafeFailure("single_update_exceeds_bulk_budget")
        if pending and (len(pending) >= MAX_DOCS or len(payload) + len(pair) > MAX_BYTES):
            yield pending, bytes(payload)
            pending, payload = [], bytearray()
        pending.append(update)
        payload.extend(pair)
    if pending:
        yield pending, bytes(payload)


def apply_batch(target, index, updates, bulk_gzip=False):
    """Raise on ANY partial error. Caller must not advance the batch offset."""
    for records, payload in bulk_parts(index, updates):
        # Split and enforce budgets before compression. Transport compression
        # changes neither the CAS actions nor acknowledged-batch boundaries.
        headers = {"Content-Type": "application/x-ndjson"}
        wire_payload = payload
        if bulk_gzip:
            wire_payload = gzip.compress(payload, compresslevel=1, mtime=0)
            headers["Content-Encoding"] = "gzip"
        response = target.call("POST", "/_bulk", data=wire_payload, headers=headers)
        items = response.get("items", [])
        if len(items) != len(records):
            raise SafeFailure("bulk_item_count_mismatch")
        failed = []
        for record, item in zip(records, items):
            result = item.get("update", {})
            if (result.get("_id") != record["_id"] or result.get("_index") != index
                    or result.get("status") not in (200, 201) or result.get("error")
                    or result.get("result") not in ("updated", "noop")):
                failed.append({"id": record["_id"], "status": result.get("status")})
        if failed or response.get("errors"):
            raise SafeFailure("bulk_partial_failure:" + json.dumps(failed, separators=(",", ":")))


def verify_samples(target, index, samples):
    if not samples:
        return []
    current, indexed = target.read(index, [s["_id"] for s in samples])
    results = []
    for sample in samples:
        ident = sample["_id"]
        doc, hit = current.get(ident), indexed.get(ident)
        ok = (bool(doc and doc.get("found")) and version(doc) is not None
              and version(doc) == version(hit)
              and text_signature(doc.get("_source", {})) == sample["text_signature"])
        fields = {f: bool(hit and equal_vectors(v, field_vector(hit, f)))
                  for f, v in sample["doc"].items()}
        for field in sample.get("required_existing", []):
            fields[field] = bool(hit and valid_vector(field_vector(hit, field)))
        ok = ok and all(fields.values())
        results.append({"id": ident, "passed": ok, "fields_equal": fields,
                        "expected_shapes": {f: len(v) for f, v in sample["doc"].items()}})
    if not all(r["passed"] for r in results):
        raise SafeFailure("post_write_sample_verification_failed")
    return results


def records_from(path):
    with gzip.open(path, "rb") as f:
        for line in f:
            record = decode(line)
            if not isinstance(record, dict) or not isinstance(record.get("_source"), dict) or "_id" not in record:
                raise SafeFailure("invalid_local_dump_record")
            yield record


def merged_records(path, overrides):
    seen = set()
    for record in records_from(path):
        ident = str(record["_id"])
        if ident in seen:
            raise SafeFailure("duplicate_base_dump_id")
        seen.add(ident)
        yield overrides.get(ident, record)
    for ident in sorted(overrides.keys() - seen):
        yield overrides[ident]


def load_inputs(args):
    plan = json.loads(Path(args.shard_plan).read_text())
    selected = {r["source_index"]: r for r in plan["selected"] if r["provider"] == "serverless"}
    if len(selected) != 81:
        raise SafeFailure("expected_81_serverless_indices_in_plan")
    requested = args.indices or list(selected)
    if len(set(requested)) != len(requested) or set(requested) - selected.keys():
        raise SafeFailure("indices_outside_serverless_plan_or_duplicate")
    priorities = {"mercado": 0, "wayfair": 1, "mercado_local": 2}
    names = sorted(requested, key=lambda name: (priorities.get(name, 3), name))
    baseline = {}
    for path in (Path(args.dump_dir) / "states").glob("*.json"):
        state = json.loads(path.read_text())
        if state.get("source_index") in names:
            baseline[state["source_index"]] = state
    if set(baseline) != set(names):
        raise SafeFailure("missing_baseline_checkpoint")
    inc = json.loads(Path(args.incremental_manifest).read_text())
    report = json.loads(Path(args.incremental_report).read_text())
    if (not inc.get("ready_for_import") or not report.get("all_pass")
            or Path(report.get("manifest", "")).resolve() != Path(args.incremental_manifest).resolve()):
        raise SafeFailure("incremental_import_not_verified")
    overrides = {name: {} for name in names}
    for row in inc["indices"]:
        name = row["source_index"]
        if name not in overrides:
            continue
        info = row["delta_dump"]
        if file_sha(info["file"]) != info["sha256"]:
            raise SafeFailure("incremental_dump_sha_mismatch")
        records = list(records_from(info["file"]))
        if len(records) != info["records"] or len({str(r["_id"]) for r in records}) != len(records):
            raise SafeFailure("incremental_dump_count_or_duplicate_id")
        overrides[name] = {str(r["_id"]): r for r in records}
    identity = {"names": names, "baseline_sha": {n: baseline[n]["sha256"] for n in names},
                "incremental_manifest_sha": file_sha(args.incremental_manifest),
                "incremental_report_sha": file_sha(args.incremental_report)}
    return names, selected, baseline, overrides, identity


def run(args):
    names, selected, baseline, overrides, identity = load_inputs(args)
    config = json.loads(Path(args.target_config).read_text())
    endpoint = config["providers"]["serverless"]
    # Bind resume to the same configured endpoint without storing the endpoint.
    identity["endpoint_sha256"] = digest(endpoint.get("hosts") or endpoint.get("host"))
    identity["apply"] = args.apply
    job_hash = digest(identity)
    state_path = Path(args.state)
    if state_path.exists():
        if not args.resume:
            raise SafeFailure("checkpoint_exists_use_resume_or_new_state")
        state = json.loads(state_path.read_text())
        if state.get("job_sha256") != job_hash:
            raise SafeFailure("checkpoint_input_or_mode_mismatch")
    else:
        if args.resume:
            raise SafeFailure("resume_checkpoint_missing")
        state = {"created_at": now(), "job_sha256": job_hash, "apply": args.apply,
                 "reads_old_es": False, "indices": {}, "status": "running"}
    target = Target(endpoint)
    checked_this_run = 0
    try:
        for name in names:
            progress = state["indices"].setdefault(name, {"offset": 0, "counters": {}, "skips": []})
            if progress.get("complete"):
                continue
            if args.limit is not None and checked_this_run >= args.limit:
                break
            base = baseline[name]
            path = Path(selected[name]["dump_file"])
            if path.resolve() != Path(base["file"]).resolve() or file_sha(path) != base["sha256"]:
                raise SafeFailure("baseline_dump_path_or_sha_mismatch")
            progress["mapping"] = target.preflight(name)
            progress.setdefault("counts_before", target.counts(name))
            iterator = enumerate(merged_records(path, overrides[name]))
            batch, samples = [], []
            anchors = {a["id"]: a for a in progress.get("verification_anchors", [])}
            exhausted = True

            def commit(records, end_offset):
                nonlocal checked_this_run
                docs, indexed = target.read(name, [str(r["_id"]) for r in records])
                updates, skipped = [], []
                for record in records:
                    ident = str(record["_id"])
                    update, reason = decide(record, docs.get(ident), indexed.get(ident))
                    if update:
                        updates.append(update)
                    else:
                        skipped.append({"id": ident, "reason": reason})
                if args.apply:
                    apply_batch(target, name, updates, bulk_gzip=getattr(args, "bulk_gzip", False))
                # This is the only input-offset advancement; every bulk item in
                # this batch has now been acknowledged, or this was a dry run.
                counters = Counter(progress["counters"])
                counters["checked"] += len(records)
                counters["updated" if args.apply else "would_update"] += len(updates)
                for update in updates:
                    counters.update("restored_" + field for field in update["added"])
                counters.update(item["reason"] for item in skipped)
                progress["counters"] = dict(counters)
                progress["skips"].extend(s for s in skipped if s["reason"] in BAD_SKIPS)
                progress["offset"] = end_offset
                progress["last_acknowledged_at"] = now()
                for update in updates:
                    if len(anchors) >= 10:
                        break
                    if update["_id"] not in anchors:
                        anchors[update["_id"]] = {
                            "id": update["_id"], "added": update["added"],
                            "required_existing": sorted(set(update["doc"]) - set(update["added"])),
                            "text_signature": update["text_signature"],
                        }
                progress["verification_anchors"] = list(anchors.values())
                state["status"] = "running"
                state.pop("error", None)
                save(state_path, state)
                checked_this_run += len(records)
                samples.extend(updates[:max(0, 10 - len(samples))])
                print(json.dumps({"index": name, "offset": end_offset, "checked": len(records),
                                  "updates": len(updates), "skipped": dict(Counter(x['reason'] for x in skipped)),
                                  "apply": args.apply}), flush=True)

            for position, record in iterator:
                if position < progress["offset"]:
                    # Reconstruct pending verification after a crash without
                    # storing vectors or document text in the checkpoint.
                    anchor = anchors.get(str(record["_id"]))
                    if anchor and len(samples) < 10:
                        samples.append({"_id": anchor["id"],
                                        "doc": {f: record["_source"][f] for f in anchor["added"]},
                                        "required_existing": anchor["required_existing"],
                                        "text_signature": anchor["text_signature"]})
                    continue
                if args.limit is not None and checked_this_run + len(batch) >= args.limit:
                    exhausted = False
                    break
                batch.append(record)
                if len(batch) == MAX_DOCS:
                    commit(batch, position + 1)
                    batch = []
            if batch:
                commit(batch, progress["offset"] + len(batch))
            if args.apply:
                # Also refresh after resume with a previously acknowledged
                # batch, so crash-before-verification is recoverable.
                target.call("POST", f"/{name}/_refresh")
                progress["sample_verification"] = verify_samples(target, name, samples)
            progress["counts_after"] = target.counts(name)
            if progress["counts_after"]["docs"] != progress["counts_before"]["docs"]:
                raise SafeFailure("root_document_count_changed_during_restore")
            if args.apply:
                for field in ROOTS:
                    minimum = progress["counts_before"][field] + progress["counters"].get("restored_" + field, 0)
                    if progress["counts_after"][field] < minimum:
                        raise SafeFailure("root_vector_count_below_acknowledged_restores")
            progress["complete"] = exhausted
            progress["verified_at"] = now()
            save(state_path, state)
        bad = sum(len(p.get("skips", [])) for p in state["indices"].values())
        state["status"] = ("completed_with_skips" if bad else "complete") if all(
            state["indices"].get(n, {}).get("complete") for n in names) else "limited"
        state["finished_at"] = now()
        save(state_path, state)
        print(json.dumps({"status": state["status"], "checked_this_run": checked_this_run,
                          "blocked_records": bad, "state": str(state_path), "apply": args.apply}), flush=True)
        return 2 if bad else 0
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = str(exc) if isinstance(exc, SafeFailure) else type(exc).__name__
        state["failed_at"] = now()
        save(state_path, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-config", default="config/config_es_runtime.local.json")
    parser.add_argument("--dump-dir", default="migration_runs/local_dump_20261001/data")
    parser.add_argument("--shard-plan", default="migration_runs/local_dump_20261001/data/shard_plan_1g.json")
    parser.add_argument("--incremental-manifest", default="migration_runs/incremental_local_20261002T161500Z/manifest.json")
    parser.add_argument("--incremental-report", default="migration_runs/incremental_local_20261002T161500Z/import_report.json")
    parser.add_argument("--indices", nargs="+")
    parser.add_argument("--limit", type=int, help="maximum documents examined in this invocation")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--bulk-gzip", action="store_true", help="gzip level 1 for bulk request bodies only")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--state", default="artifacts/root_vector_restore_checkpoint.json")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc) if isinstance(exc, SafeFailure)
                          else type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
