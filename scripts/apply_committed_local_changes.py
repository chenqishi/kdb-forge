#!/usr/bin/env python3
"""Consume sealed local changes. Default dry-run has no network or state writes.

This is a target-side consumer, not a source CDC producer or freshness proof.
Run only under coordinated exclusive target ownership; never alongside another
writer/rebuild. Existing exact physical names are checked before every bulk;
external administrators must not delete/recreate indices during this window.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_es7_to_es8 import ESHttp

CONTRACT = "es8-committed-changes-v1"
ROOTS = ("title_embedding", "content_embedding")
NESTED = ("indexes", "image_indexes")
MAX_DOCS, MAX_BYTES = 32, 2 * 1024 * 1024
MAX_LINE = 16 * 1024 * 1024
INT64_MAX = 2**63 - 1
DEFAULT_PLAN = "migration_runs/local_dump_20261001/data/shard_plan_1g.json"
DEFAULT_LEASE = "artifacts/root_restore_target_write_lease_20261004.json"


class SafeFailure(RuntimeError):
    """Contains only sanitized status/category, never response text or documents."""


def require(condition, reason):
    if not condition:
        raise SafeFailure(reason)


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=no_duplicates,
                          parse_constant=lambda _: (_ for _ in ()).throw(SafeFailure("nonfinite_json")))
    except (ValueError, UnicodeError, RecursionError):
        raise SafeFailure("invalid_json") from None


def read_json(path):
    return decode(Path(path).read_bytes())


def atomic_save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(encoded(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def valid_vector(value):
    if not isinstance(value, list) or len(value) != 1024:
        return False
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in value):
        return False
    try:
        floats = struct.unpack("<1024f", struct.pack("<1024f", *value))
    except (OverflowError, struct.error):
        return False
    return all(math.isfinite(v) for v in floats) and any(v != 0 for v in floats)


def validate_source(source):
    require(isinstance(source, dict), "after_image_not_object")
    for field in ROOTS:
        if field in source:
            require(valid_vector(source[field]), "invalid_root_vector")
    for field in NESTED:
        if field not in source:
            continue
        rows = source[field]
        # ES permits a singleton nested object as well as an array of objects.
        rows = [rows] if isinstance(rows, dict) else rows
        require(isinstance(rows, list), "invalid_nested_container")
        for row in rows:
            require(isinstance(row, dict), "invalid_nested_object")
            if "embedding" in row:
                require(valid_vector(row["embedding"]), "invalid_nested_vector")


def load_plan(path):
    raw = Path(path).read_bytes()
    data = decode(raw)
    rows = data.get("selected", [])
    require(len(rows) == 86 and data.get("selected_count") == 86, "approved_plan_must_have_86_indices")
    plan = {}
    for row in rows:
        name, provider = row.get("source_index"), row.get("provider")
        require(isinstance(name, str) and re.fullmatch(r"[a-z0-9_][a-z0-9_.-]*", name)
                and "__v817" not in name and name not in plan, "invalid_approved_index")
        require(provider in ("paas", "serverless"), "invalid_provider")
        plan[name] = provider
    require(list(plan.values()).count("paas") == 5 and list(plan.values()).count("serverless") == 81,
            "approved_provider_counts_mismatch")
    return plan, sha(raw)


def endpoint_binding(config, plan):
    result = {}
    for provider in sorted(set(plan.values())):
        cfg = config.get("providers", {}).get(provider, {})
        hosts = cfg.get("hosts") or cfg.get("host")
        hosts = [hosts] if isinstance(hosts, str) else hosts
        require(isinstance(hosts, list) and hosts, "missing_target_endpoint")
        for host in hosts:
            parsed = urlsplit(host)
            require(parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username
                    and not parsed.password and not parsed.query and not parsed.fragment,
                    "invalid_target_endpoint")
        result[provider] = sha(encoded(sorted(h.rstrip("/") for h in hosts)))
    return result


class Window:
    """Two streaming passes; only last-cursor metadata is retained in memory."""
    def __init__(self, manifest_path, plan, plan_sha):
        self.path = Path(manifest_path).resolve()
        raw = self.path.read_bytes()
        self.manifest_sha = sha(raw)
        self.m = decode(raw)
        m = self.m
        require(m.get("contract") == CONTRACT and m.get("status") == "committed", "uncommitted_manifest")
        require(m.get("approved_plan_sha256") == plan_sha, "approved_plan_sha_mismatch")
        require(isinstance(m.get("stream_id"), str) and 0 < len(m["stream_id"]) <= 200, "invalid_stream_id")
        for key in ("version_base", "start_exclusive", "end_inclusive", "records"):
            require(integer(m.get(key)) and m[key] >= 0, "invalid_window_integer")
        require(m["version_base"] > 0 and m["end_inclusive"] >= m["start_exclusive"]
                and m["version_base"] + m["end_inclusive"] <= INT64_MAX, "invalid_version_window")
        require(isinstance(m.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", m["sha256"]), "invalid_file_sha")
        name = m.get("file")
        require(isinstance(name, str) and Path(name).name == name and name.endswith(".gz"), "invalid_local_log_path")
        self.file = self.path.parent / name
        require(not self.file.is_symlink() and self.file.is_file(), "log_not_regular_frozen_file")
        self.plan, self.last, self.indices = plan, {}, set()
        self.fingerprint = None

    def check_file(self):
        stat = self.file.stat()
        fingerprint = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        require(self.fingerprint is None or self.fingerprint == fingerprint, "frozen_log_changed")
        require(sha(self.path.read_bytes()) == self.manifest_sha, "frozen_manifest_changed")
        h = hashlib.sha256()
        with self.file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        require(h.hexdigest() == self.m["sha256"], "compressed_log_sha_mismatch")
        self.fingerprint = fingerprint

    def events(self):
        try:
            with gzip.open(self.file, "rb") as handle:
                while True:
                    line = handle.readline(MAX_LINE + 1)
                    if not line:
                        break
                    require(len(line) <= MAX_LINE and line.endswith(b"\n"), "oversized_or_unterminated_record")
                    event = decode(line)
                    require(isinstance(event, dict), "event_not_object")
                    yield event
        except (OSError, EOFError):
            raise SafeFailure("invalid_gzip_log") from None

    def validate(self):
        self.check_file()
        previous, count = self.m["start_exclusive"], 0
        for event in self.events():
            cursor, index = event.get("cursor"), event.get("index")
            require(event.get("stream_id") == self.m["stream_id"], "event_stream_mismatch")
            require(integer(cursor) and previous < cursor <= self.m["end_inclusive"], "cursor_not_strictly_increasing")
            require(isinstance(index, str) and index in self.plan and "__v817" not in index, "index_not_approved")
            require(event.get("provider") == self.plan[index], "event_provider_mismatch")
            require(isinstance(event.get("id"), str) and 0 < len(event["id"].encode()) <= 512, "invalid_document_id")
            require(event.get("op") in ("upsert", "delete"), "invalid_operation")
            require(set(event) <= {"stream_id", "cursor", "provider", "index", "id", "op", "after"},
                    "unsupported_event_field")
            if event["op"] == "upsert":
                validate_source(event.get("after"))
            else:
                require("after" not in event, "delete_has_after_image")
            require(len(event_payload(event, self.m["version_base"])) <= MAX_BYTES, "single_event_exceeds_bulk_budget")
            self.last[(index, event["id"])] = cursor
            self.indices.add(index)
            previous, count = cursor, count + 1
        require(count == self.m["records"] and previous == self.m["end_inclusive"], "closed_window_count_or_end_mismatch")
        self.check_file()
        return self

    def final_events(self):
        self.check_file()
        for event in self.events():
            if self.last[(event["index"], event["id"])] == event["cursor"]:
                yield event


def event_payload(event, version_base):
    operation = "index" if event["op"] == "upsert" else "delete"
    action = {operation: {"_index": event["index"], "_id": event["id"],
                          "version": version_base + event["cursor"], "version_type": "external_gte"}}
    return encoded(action) + b"\n" + (encoded(event["after"]) + b"\n" if operation == "index" else b"")


def batches(events, version_base):
    pending, payload, provider = [], bytearray(), None
    for event in events:
        part = event_payload(event, version_base)
        require(len(part) <= MAX_BYTES, "single_event_exceeds_bulk_budget")
        if pending and (len(pending) == MAX_DOCS or len(payload) + len(part) > MAX_BYTES
                        or provider != event["provider"]):
            yield provider, pending, bytes(payload)
            pending, payload = [], bytearray()
        provider = event["provider"]
        pending.append(event)
        payload.extend(part)
    if pending:
        yield provider, pending, bytes(payload)


def lease_guard(path, affected):
    if not affected:
        return
    require(Path(path).is_file(), "serverless_restore_lease_missing")
    lease = read_json(path)
    require(lease.get("provider") == "serverless" and isinstance(lease.get("indices"), list)
            and lease["indices"] and all(isinstance(i, str) and i for i in lease["indices"]), "invalid_restore_lease")
    overlap = affected.intersection(lease["indices"])
    require(lease.get("status") in ("active", "released"), "unknown_restore_lease_status")
    require(not overlap or lease["status"] == "released", "serverless_restore_lease_active")


class Target:
    def __init__(self, config):
        self.client = ESHttp(config, timeout=120)
        self.source_excludes = {}

    def call(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except Exception as exc:
            raise SafeFailure(f"target_transport_{type(exc).__name__}") from None
        require(response.ok, f"target_http_{response.status_code}")
        try:
            body = response.json()
        except ValueError:
            raise SafeFailure("target_non_json_response") from None
        require(isinstance(body, dict) and not body.get("timed_out")
                and not (body.get("_shards") or {}).get("failed", 0), "target_partial_response")
        return body

    def identity(self, index):
        body = self.call("GET", f"/{quote(index)}/_settings", params={"flat_settings": "true"})
        require(set(body) == {index}, "target_not_exact_physical_index")
        uuid = body[index].get("settings", {}).get("index.uuid")
        require(isinstance(uuid, str) and uuid, "target_uuid_missing")
        return uuid

    def preflight(self, index):
        uuid = self.identity(index)
        body = self.call("GET", f"/{quote(index)}/_mapping")
        require(set(body) == {index}, "target_mapping_not_exact_index")
        mapping = body[index].get("mappings", {})
        require(not mapping.get("_routing", {}).get("required"), "custom_routing_not_supported")
        source = mapping.get("_source", {})
        require(source.get("enabled") is not False and not source.get("includes")
                and not set(source.get("excludes", [])) - set(ROOTS), "unsupported_source_filter")
        self.source_excludes[index] = set(source.get("excludes", []))
        props = mapping.get("properties", {})
        vectors = [props.get(key, {}) for key in ROOTS]
        for key in NESTED:
            require(props.get(key, {}).get("type") == "nested", "unsupported_nested_mapping")
            vectors.append(props[key].get("properties", {}).get("embedding", {}))
        require(all(v.get("type") == "dense_vector" and v.get("dims") == 1024
                    and v.get("similarity", "cosine") == "cosine"
                    and v.get("element_type", "float") == "float" and v.get("index") is True
                    for v in vectors), "unsupported_vector_mapping")
        return uuid

    def bulk(self, events, payload, version_base):
        body = self.call("POST", "/_bulk",
                         data=gzip.compress(payload, compresslevel=1, mtime=0),
                         headers={"Content-Type": "application/x-ndjson", "Content-Encoding": "gzip"})
        items = body.get("items", [])
        require(len(items) == len(events), "bulk_item_count_mismatch")
        for event, item in zip(events, items):
            operation = "index" if event["op"] == "upsert" else "delete"
            result = item.get(operation, {})
            status = result.get("status")
            require(integer(status), "bulk_status_missing")
            allowed = (200, 201) if operation == "index" else (200, 404)
            require(status in allowed and not result.get("error"), f"bulk_item_failed_status_{status}")
            require(status != 404 or result.get("result") == "not_found", "delete_404_not_tombstone_ack")
            require(not (result.get("_shards") or {}).get("failed", 0), "bulk_item_shard_failure")
            require(result.get("_index") == event["index"] and result.get("_id") == event["id"]
                    and result.get("_version") == version_base + event["cursor"], "bulk_ack_identity_or_version_mismatch")

    def refresh(self, indices):
        self.call("POST", f"/{','.join(quote(i) for i in sorted(indices))}/_refresh")

    def verify(self, events, version_base):
        for index in sorted({e["index"] for e in events}):
            group = [e for e in events if e["index"] == index]
            body = self.call("POST", f"/{quote(index)}/_mget", json={"ids": [e["id"] for e in group]})
            docs = body.get("docs", [])
            require(len(docs) == len(group), "verify_mget_count_mismatch")
            by_id = {d.get("_id"): d for d in docs}
            require(len(by_id) == len(group) and set(by_id) == {e["id"] for e in group}, "verify_mget_ids_mismatch")
            upserts = [e for e in group if e["op"] == "upsert"]
            hits = {}
            if upserts:
                search = self.call("POST", f"/{quote(index)}/_search", json={
                    "size": len(upserts), "track_total_hits": True, "_source": False,
                    "version": True, "seq_no_primary_term": True, "docvalue_fields": list(ROOTS),
                    "query": {"ids": {"values": [e["id"] for e in upserts]}},
                })
                rows = search.get("hits", {}).get("hits", [])
                hits = {h.get("_id"): h for h in rows}
                require(len(rows) == len(upserts) and len(hits) == len(upserts), "verify_search_count_mismatch")
            for event in group:
                doc = by_id[event["id"]]
                require(not doc.get("error") and doc.get("_index") == index, "verify_mget_item_error")
                if event["op"] == "delete":
                    require(doc.get("found") is False, "verify_delete_still_present")
                    continue
                hit = hits.get(event["id"], {})
                wanted = version_base + event["cursor"]
                require(doc.get("found") is True and doc.get("_version") == wanted
                        and hit.get("_version") == wanted and hit.get("_index") == index,
                        "verify_version_or_presence_mismatch")
                require(all(integer(doc.get(k)) and doc.get(k) == hit.get(k)
                            for k in ("_seq_no", "_primary_term")), "verify_mixed_document_versions")
                actual = doc.get("_source")
                require(isinstance(actual, dict), "verify_source_missing")
                expected_source = dict(event["after"])
                excluded = getattr(self, "source_excludes", {}).get(index, set())
                for key in ROOTS:
                    value = hit.get("fields", {}).get(key)
                    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
                        value = value[0]
                    require((key in event["after"]) == (value is not None), "verify_root_indexed_presence_mismatch")
                    if value is not None:
                        # Indexed cosine vectors may be normalized, independent
                        # of their original values in stored _source.
                        require(vector_equal(event["after"][key], value), "verify_indexed_root_direction_mismatch")
                        if key not in actual:
                            require(key in excluded, "verify_unfiltered_source_root_missing")
                            expected_source.pop(key)
                # Never replace a present stored vector with docvalues: doing
                # so could hide corruption such as a 2x vector magnitude.
                require(equal_source(expected_source, actual), "verify_content_or_vector_mismatch")


def vector_equal(left, right):
    if not valid_vector(left) or not valid_vector(right):
        return False
    # Float32 indexed values may be cosine-normalized by ES. Compare direction;
    # magnitude remains significant only in the stored business source.
    left_norm = math.sqrt(sum(float(v) ** 2 for v in left))
    right_norm = math.sqrt(sum(float(v) ** 2 for v in right))
    return all(abs(a / left_norm - b / right_norm) <= 2e-6 for a, b in zip(left, right))


def stored_vector_equal(left, right):
    return (valid_vector(left) and valid_vector(right)
            and all(abs(float(a) - float(b)) <= 1e-6 for a, b in zip(left, right)))


def equal_source(expected, actual, vector=False, path=()):
    if vector:
        return stored_vector_equal(expected, actual)
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            return False
        return all(equal_source(value, actual[key],
                                vector=(not path and key in ROOTS) or (key == "embedding" and path in [("indexes",), ("image_indexes",)]),
                                path=path + (key,)) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            equal_source(a, b, path=path) for a, b in zip(expected, actual))
    # Do not consider JSON true and 1 equal.
    return type(expected) is type(actual) and expected == actual or (
        not isinstance(expected, bool) and not isinstance(actual, bool)
        and isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and expected == actual)


def prepare_state(path, window, bindings, initial_cursor):
    if Path(path).exists():
        state = read_json(path)
        require(state.get("contract") == CONTRACT and state.get("bindings") == bindings, "state_binding_mismatch")
        identities = state.get("index_uuids")
        require(isinstance(identities, dict) and all(isinstance(k, str) and isinstance(v, str) and v
                                                    for k, v in identities.items()), "state_uuid_binding_missing")
        cursor = state.get("applied_cursor")
        require(integer(cursor) and cursor >= 0, "invalid_applied_cursor")
        pending = state.get("pending")
        if pending:
            require(pending.get("manifest_sha256") == window.manifest_sha, "different_window_pending")
            require(pending.get("start_exclusive") == window.m["start_exclusive"]
                    and pending.get("end_inclusive") == window.m["end_inclusive"], "pending_window_bounds_mismatch")
        if cursor == window.m["end_inclusive"] and state.get("last_manifest_sha256") == window.manifest_sha and not pending:
            return state, True
    else:
        require(integer(initial_cursor) and initial_cursor >= 0, "explicit_initial_cursor_required")
        state = {"contract": CONTRACT, "bindings": bindings, "applied_cursor": initial_cursor,
                 "freshness_proven": False, "pending": None, "index_uuids": {}}
    require(state["applied_cursor"] == window.m["start_exclusive"], "window_gap_or_out_of_order")
    return state, False


def canonical_paths(plan, endpoints):
    # Scope means actual index/provider pairs, not formatting/metadata in the
    # plan file. Reformatting a plan must not create a new replay namespace.
    key = sha(encoded({"scope": plan, "endpoints": endpoints}))
    base = Path(__file__).resolve().parents[1] / "artifacts" / f"committed_consumer_{key}"
    return base.with_suffix(".lock"), base.with_suffix(".registry.json")


def register_state(registry_path, state_path, state, bindings, persist):
    """Bind one durable state to the target scope; repair only proven lag.

    Final commit order is verified state first, registry second. If interrupted
    between them, registry.pending identifies exactly which already-verified
    state advance is allowed. A registry ahead of state always fails closed.
    """
    registry_path, state_path = Path(registry_path), Path(state_path).resolve()
    if not registry_path.exists():
        require(not state.get("pending") and not state.get("last_manifest_sha256")
                and not state.get("index_uuids"), "canonical_registry_missing_for_existing_state")
        registry = {"contract": CONTRACT, "bindings": bindings, "state_path": str(state_path),
                    "applied_cursor": state["applied_cursor"], "pending": None,
                    "last_manifest_sha256": None}
        if persist:
            # No ES writes precede registration. A crash here can leave only a
            # pristine state, which is safe to register on the next invocation.
            if not state_path.exists():
                atomic_save(state_path, state)
            atomic_save(registry_path, registry)
        return registry
    registry = read_json(registry_path)
    require(registry.get("contract") == CONTRACT and registry.get("bindings") == bindings,
            "canonical_registry_binding_mismatch")
    require(registry.get("state_path") == str(state_path), "canonical_registry_other_state_path")
    require(state_path.is_file(), "registered_state_missing")
    cursor = registry.get("applied_cursor")
    require(integer(cursor) and 0 <= cursor <= state["applied_cursor"], "canonical_registry_ahead_of_state")
    if (cursor < state["applied_cursor"]
            or registry.get("last_manifest_sha256") != state.get("last_manifest_sha256")):
        pending = registry.get("pending") or {}
        require(pending.get("start_exclusive") == cursor
                and pending.get("end_inclusive") == state["applied_cursor"]
                and pending.get("manifest_sha256") == state.get("last_manifest_sha256")
                and state.get("last_manifest_sha256") and state.get("last_applied_at")
                and state.get("pending") is None, "unproven_state_advance")
        registry.update(applied_cursor=state["applied_cursor"], pending=None,
                        last_manifest_sha256=state["last_manifest_sha256"])
        if persist:
            atomic_save(registry_path, registry)
    require(registry.get("last_manifest_sha256") == state.get("last_manifest_sha256"),
            "canonical_registry_history_mismatch")
    return registry


def bind_pending_registry(registry_path, registry, window):
    pending = {"manifest_sha256": window.manifest_sha,
               "start_exclusive": window.m["start_exclusive"], "end_inclusive": window.m["end_inclusive"]}
    require(registry.get("pending") in (None, pending), "canonical_registry_different_pending_window")
    registry["pending"] = pending
    atomic_save(registry_path, registry)


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafeFailure("another_consumer_holds_target_lock") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def consume(args, target_factory=Target):
    plan, plan_sha = load_plan(args.plan)
    config = read_json(args.config)
    window = Window(args.manifest, plan, plan_sha).validate()
    bindings = {"stream_id": window.m["stream_id"], "version_base": window.m["version_base"],
                "approved_plan_sha256": plan_sha, "target_endpoint_sha256": endpoint_binding(config, plan)}
    lock_path, registry_path = canonical_paths(plan, bindings["target_endpoint_sha256"])
    state_path = Path(args.state).resolve()
    state, done = prepare_state(state_path, window, bindings, args.initial_cursor)
    report = {"mode": "apply" if args.apply else "dry_run", "records": window.m["records"],
              "final_ids": len(window.last), "indices": len(window.indices), "freshness_proven": False,
              "start_exclusive": window.m["start_exclusive"], "end_inclusive": window.m["end_inclusive"],
              "already_applied": done, "applied_cursor": state["applied_cursor"]}
    if not args.apply:
        registry = register_state(registry_path, state_path, state, bindings, persist=False)
        pending = {"manifest_sha256": window.manifest_sha, "start_exclusive": window.m["start_exclusive"],
                   "end_inclusive": window.m["end_inclusive"]}
        require(registry.get("pending") in (None, pending), "canonical_registry_different_pending_window")
        return report
    with exclusive_lock(lock_path):
        state, done = prepare_state(state_path, window, bindings, args.initial_cursor)
        affected = {i for i in window.indices if plan[i] == "serverless"}
        lease_guard(args.lease, affected)
        registry = register_state(registry_path, state_path, state, bindings, persist=True)
        if done:
            report.update(already_applied=True, applied_cursor=state["applied_cursor"])
            return report
        # Persist the sealed window in both journals before any target writes.
        # Registry first: a crash cannot allow a different same-cursor window.
        bind_pending_registry(registry_path, registry, window)
        targets = {p: target_factory(config["providers"][p]) for p in {plan[i] for i in window.indices}}
        identities = dict(state.get("index_uuids", {}))
        for index in sorted(window.indices):
            uuid = targets[plan[index]].preflight(index)
            require(index not in identities or identities[index] == uuid, "target_index_replaced")
            identities[index] = uuid
        state["index_uuids"] = identities
        state["pending"] = {"manifest_sha256": window.manifest_sha,
                            "start_exclusive": window.m["start_exclusive"], "end_inclusive": window.m["end_inclusive"]}
        state["freshness_proven"] = False
        atomic_save(state_path, state)
        count = 0
        for provider, events, payload in batches(window.final_events(), window.m["version_base"]):
            lease_guard(args.lease, affected)
            target = targets[provider]
            for index in sorted({e["index"] for e in events}):
                require(target.identity(index) == identities[index], "target_index_missing_or_replaced")
            target.bulk(events, payload, window.m["version_base"])
            count += len(events)
        require(count == len(window.last), "final_id_count_mismatch")
        lease_guard(args.lease, affected)
        # Refresh once per provider after all ACKs, then a third local streaming
        # pass verifies every final ID. Never wait for refresh per 32-doc bulk.
        for provider, target in targets.items():
            indices = {i for i in window.indices if plan[i] == provider}
            for index in sorted(indices):
                require(target.identity(index) == identities[index], "target_index_missing_or_replaced")
            target.refresh(indices)
        verified = 0
        for provider, events, _ in batches(window.final_events(), window.m["version_base"]):
            lease_guard(args.lease, affected)
            targets[provider].verify(events, window.m["version_base"])
            verified += len(events)
        require(verified == count, "verified_id_count_mismatch")
        lease_guard(args.lease, affected)
        window.check_file()
        state.update(applied_cursor=window.m["end_inclusive"], pending=None,
                     last_manifest_sha256=window.manifest_sha,
                     last_applied_at=datetime.now(timezone.utc).isoformat(), freshness_proven=False)
        atomic_save(state_path, state)
        registry.update(applied_cursor=state["applied_cursor"], pending=None,
                        last_manifest_sha256=state["last_manifest_sha256"])
        atomic_save(registry_path, registry)
        report.update(applied_cursor=state["applied_cursor"], verified_final_ids=verified)
        return report


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", required=True)
    result.add_argument("--state", required=True)
    result.add_argument("--plan", default=DEFAULT_PLAN)
    result.add_argument("--config", default="config/config_es_runtime.local.json")
    result.add_argument("--lease", default=DEFAULT_LEASE)
    result.add_argument("--initial-cursor", type=int, help="Required only for a new local state; does not certify baseline coverage")
    result.add_argument("--apply", action="store_true", help="Enable new-target reads/writes; requires coordinated exclusive writer window")
    return result


def main():
    try:
        print(encoded(consume(parser().parse_args())).decode())
        return 0
    except SafeFailure as exc:
        print(encoded({"status": "failed", "reason": str(exc), "freshness_proven": False}).decode(), file=sys.stderr)
        return 2
    except Exception as exc:
        print(encoded({"status": "failed", "reason": f"local_{type(exc).__name__}", "freshness_proven": False}).decode(), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
