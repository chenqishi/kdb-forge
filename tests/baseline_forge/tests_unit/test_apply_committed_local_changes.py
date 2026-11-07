"""Offline-only contract/replay gates; never instantiate real network clients."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply_committed_local_changes.py"
spec = importlib.util.spec_from_file_location("committed_consumer", SCRIPT)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def vector(value=0.1):
    return [value] * 1024


def event(cursor=1, op="upsert", index="paas_0", ident="same"):
    row = {"stream_id": "test-stream", "cursor": cursor, "provider": "paas" if index.startswith("paas_") else "serverless",
           "index": index, "id": ident, "op": op}
    if op == "upsert":
        row["after"] = {"title": "private body", "title_embedding": vector(),
                        "indexes": [{"embedding": vector(0.2), "text": "private nested"}]}
    return row


@pytest.fixture
def setup(tmp_path, monkeypatch):
    original_lock = c.exclusive_lock
    monkeypatch.setattr(c, "exclusive_lock", lambda _: original_lock(tmp_path / "consumer.lock"))
    monkeypatch.setattr(c, "canonical_paths", lambda plan, endpoints: (tmp_path / "consumer.lock", tmp_path / "registry.json"))
    plan = {"selected_count": 86, "selected": [{"source_index": f"{provider}_{i}", "provider": provider}
            for provider, size in [("paas", 5), ("serverless", 81)] for i in range(size)]}
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(c.encoded(plan))
    config = tmp_path / "config.json"
    config.write_bytes(c.encoded({"providers": {p: {"host": f"https://{p}.invalid", "username": "u", "password": "secret"}
                                              for p in ("paas", "serverless")}}))
    lease = tmp_path / "lease.json"
    lease.write_bytes(c.encoded({"provider": "serverless", "status": "released",
                                "indices": [f"serverless_{i}" for i in range(81)]}))
    args = SimpleNamespace(manifest=str(tmp_path / "manifest.json"), state=str(tmp_path / "state.json"),
                           plan=str(plan_path), config=str(config), lease=str(lease), initial_cursor=0, apply=False)

    def seal(events=None, **overrides):
        events = events if events is not None else [event()]
        log = tmp_path / "events.ndjson.gz"
        log.write_bytes(gzip.compress(b"".join(c.encoded(e) + b"\n" for e in events), mtime=0))
        manifest = {"contract": c.CONTRACT, "status": "committed", "stream_id": "test-stream", "version_base": 10000,
                    "start_exclusive": 0, "end_inclusive": events[-1]["cursor"] if events else 0,
                    "records": len(events), "approved_plan_sha256": c.sha(plan_path.read_bytes()),
                    "file": log.name, "sha256": c.sha(log.read_bytes())}
        manifest.update(overrides)
        Path(args.manifest).write_bytes(c.encoded(manifest))
        return args
    return args, seal


class FakeTarget:
    def __init__(self):
        self.uuid = "fixed-uuid"
        self.writes = []
        self.stored = {}
        self.fail_bulk = False
        self.fail_verify = False

    def preflight(self, index):
        return self.uuid

    def identity(self, index):
        return self.uuid

    def bulk(self, events, payload, base):
        for e in events:
            self.writes.append(copy.deepcopy(e))
            self.stored[(e["index"], e["id"])] = e
        if self.fail_bulk:
            raise c.SafeFailure("partial_bulk_failure")

    def verify(self, events, base):
        if self.fail_verify:
            raise c.SafeFailure("verification_failed")

    def refresh(self, indices):
        pass


def forbidden_factory(_):
    raise AssertionError("dry-run attempted network client")


def test_default_dry_run_zero_network_zero_state_and_final_fold(setup):
    args, seal = setup
    seal([event(), event(2, "delete")])
    report = c.consume(args, forbidden_factory)
    assert report["records"] == 2 and report["final_ids"] == 1
    assert report["applied_cursor"] == 0 and report["freshness_proven"] is False
    assert not Path(args.state).exists()


@pytest.mark.parametrize("failure", ["fail_bulk", "fail_verify"])
def test_any_failure_keeps_cursor_pending_then_local_retry_never_resurrects(setup, failure):
    args, seal = setup
    seal([event(), event(2, "delete")])
    args.apply = True
    target = FakeTarget()
    setattr(target, failure, True)
    with pytest.raises(c.SafeFailure):
        c.consume(args, lambda _: target)
    state = c.read_json(args.state)
    assert state["applied_cursor"] == 0 and state["pending"]
    assert [e["op"] for e in target.writes] == ["delete"]
    setattr(target, failure, False)
    assert c.consume(args, lambda _: target)["applied_cursor"] == 2
    assert [e["op"] for e in target.writes] == ["delete", "delete"]
    assert c.consume(args, forbidden_factory)["already_applied"] is True


@pytest.mark.parametrize("override,reason", [
    ({"sha256": "0" * 64}, "sha_mismatch"),
    ({"approved_plan_sha256": "0" * 64}, "plan_sha"),
    ({"start_exclusive": 2, "end_inclusive": 3}, "cursor_not"),
    ({"records": 2}, "count_or_end"),
    ({"end_inclusive": 5}, "count_or_end"),
    ({"status": "writing"}, "uncommitted"),
    ({"version_base": c.INT64_MAX}, "version_window"),
])
def test_corrupt_or_unsealed_window_rejected_offline(setup, override, reason):
    args, seal = setup
    seal(**override)
    with pytest.raises(c.SafeFailure, match=reason):
        c.consume(args, forbidden_factory)


@pytest.mark.parametrize("change,reason", [
    ({"provider": "serverless"}, "provider_mismatch"),
    ({"index": "paas_0__v817_old"}, "index_not_approved"),
    ({"index": "new_index"}, "index_not_approved"),
    ({"stream_id": "other"}, "stream_mismatch"),
    ({"op": "update"}, "invalid_operation"),
])
def test_invalid_event_never_reaches_target(setup, change, reason):
    args, seal = setup
    row = event()
    row.update(change)
    seal([row])
    with pytest.raises(c.SafeFailure, match=reason):
        c.consume(args, forbidden_factory)


@pytest.mark.parametrize("bad", [[0.0] * 1024, [1.0], [True] * 1024, [1e300] * 1024, [1e-300] * 1024])
def test_all_vectors_validated_even_if_followed_by_delete(setup, bad):
    args, seal = setup
    row = event()
    row["after"]["indexes"][0]["embedding"] = bad
    seal([row, event(2, "delete")])
    with pytest.raises(c.SafeFailure, match="invalid_nested_vector"):
        c.consume(args, forbidden_factory)


def test_nonfinite_and_duplicate_json_fields_rejected():
    with pytest.raises(c.SafeFailure, match="nonfinite"):
        c.decode('{"value":NaN}')
    with pytest.raises(c.SafeFailure, match="duplicate"):
        c.decode('{"cursor":1,"cursor":2}')


def test_pending_window_payload_cannot_change_at_same_cursor(setup):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    target.fail_verify = True
    with pytest.raises(c.SafeFailure):
        c.consume(args, lambda _: target)
    changed = event()
    changed["after"]["title"] = "different"
    seal([changed])
    with pytest.raises(c.SafeFailure, match="different_window_pending"):
        c.consume(args, forbidden_factory)


def test_skip_or_old_window_rejected_and_next_window_succeeds(setup):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    c.consume(args, lambda _: target)
    seal([event(3)], start_exclusive=2)
    with pytest.raises(c.SafeFailure, match="gap_or_out_of_order"):
        c.consume(args, forbidden_factory)
    seal([event(1, "delete")])
    with pytest.raises(c.SafeFailure, match="gap_or_out_of_order"):
        c.consume(args, forbidden_factory)
    seal([event(2)], start_exclusive=1)
    assert c.consume(args, lambda _: target)["applied_cursor"] == 2


@pytest.mark.parametrize("binding", ["version_base", "stream_id", "endpoint"])
def test_state_binding_changes_refused(setup, binding):
    args, seal = setup
    seal()
    args.apply = True
    c.consume(args, lambda _: FakeTarget())
    changes = {binding: "new-stream" if binding == "stream_id" else 10001} if binding != "endpoint" else {}
    row = event(2)
    if binding == "stream_id":
        row["stream_id"] = "new-stream"
    seal([row], start_exclusive=1, **changes)
    if binding == "endpoint":
        config = c.read_json(args.config)
        config["providers"]["paas"]["host"] = "https://other.invalid"
        Path(args.config).write_bytes(c.encoded(config))
    with pytest.raises(c.SafeFailure, match="binding_mismatch"):
        c.consume(args, forbidden_factory)


def test_active_lease_blocks_serverless_before_network_but_paas_allowed(setup):
    args, seal = setup
    lease = c.read_json(args.lease)
    lease["status"] = "active"
    Path(args.lease).write_bytes(c.encoded(lease))
    seal([event(index="serverless_0")])
    args.apply = True
    with pytest.raises(c.SafeFailure, match="lease_active"):
        c.consume(args, forbidden_factory)
    seal([event()])
    assert c.consume(args, lambda _: FakeTarget())["applied_cursor"] == 1


def test_missing_lease_fails_closed_for_serverless(setup):
    args, seal = setup
    seal([event(index="serverless_0")])
    args.apply = True
    Path(args.lease).unlink()
    with pytest.raises(c.SafeFailure, match="lease_missing"):
        c.consume(args, forbidden_factory)


def test_uuid_replaced_before_bulk_prevents_write(setup):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    target.identity = lambda _: "replaced"
    with pytest.raises(c.SafeFailure, match="missing_or_replaced"):
        c.consume(args, lambda _: target)
    assert not target.writes and c.read_json(args.state)["applied_cursor"] == 0


def test_bulk_gzip_preserves_external_versions_and_partial_errors_raise():
    target = object.__new__(c.Target)
    rows = [event(), event(2, "delete", ident="removed")]
    provider, events, payload = list(c.batches(rows, 10000))[0]
    captured = {}
    def call(method, path, **kwargs):
        captured.update(kwargs)
        return {"errors": True, "items": [
            {"index": {"_index": "paas_0", "_id": "same", "_version": 10001, "status": 201}},
            {"delete": {"_index": "paas_0", "_id": "removed", "status": 403,
                        "error": {"reason": "SECRET DATA"}}}]}
    target.call = call
    with pytest.raises(c.SafeFailure, match="status_403") as exc:
        target.bulk(events, payload, 10000)
    assert "SECRET" not in str(exc.value)
    assert gzip.decompress(captured["data"]) == payload
    assert captured["headers"]["Content-Encoding"] == "gzip"
    assert json.loads(payload.splitlines()[0])["index"]["version_type"] == "external_gte"


@pytest.mark.parametrize("error,result,allowed", [(None, "not_found", True),
                                                  ({"type": "index_not_found_exception"}, "not_found", False),
                                                  (None, "unexpected", False)])
def test_delete_404_only_genuine_document_not_found_is_idempotent(error, result, allowed):
    target = object.__new__(c.Target)
    row = event(op="delete")
    response = {"items": [{"delete": {"_index": row["index"], "_id": row["id"], "_version": 10001,
                                        "status": 404, "result": result, "error": error}}]}
    target.call = lambda *a, **k: response
    if allowed:
        target.bulk([row], c.event_payload(row, 10000), 10000)
    else:
        with pytest.raises(c.SafeFailure):
            target.bulk([row], c.event_payload(row, 10000), 10000)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_http_errors_not_swallowed_or_leaked(status):
    target = object.__new__(c.Target)
    class Response:
        ok = False
        status_code = status
        text = "SECRET"
    target.client = SimpleNamespace(request=lambda *a, **k: Response())
    with pytest.raises(c.SafeFailure, match=f"target_http_{status}") as exc:
        target.call("GET", "/index/_mapping")
    assert "SECRET" not in str(exc.value)


def test_batches_bounded_uncompressed_and_provider_separated():
    events = [event(i + 1, ident=str(i)) for i in range(65)] + [event(66, index="serverless_0")]
    parts = list(c.batches(events, 10000))
    assert [len(rows) for _, rows, _ in parts] == [32, 32, 1, 1]
    assert all(len(payload) <= c.MAX_BYTES for _, _, payload in parts)
    assert parts[-1][0] == "serverless"


def test_verification_reconstructs_source_roots_and_checks_version_and_every_field():
    row = event()
    source = copy.deepcopy(row["after"])
    source.pop("title_embedding")
    doc = {"_index": row["index"], "_id": row["id"], "_version": 10001, "_seq_no": 4,
           "_primary_term": 1, "found": True, "_source": source}
    hit = {k: v for k, v in doc.items() if k not in ("_source", "found")}
    hit["fields"] = {"title_embedding": [vector(1 / 32)]}
    target = object.__new__(c.Target)
    target.source_excludes = {row["index"]: {"title_embedding", "content_embedding"}}
    target.call = lambda method, path, **kwargs: {"docs": [doc]} if path.endswith("_mget") else {"hits": {"hits": [hit]}}
    target.verify([row], 10000)
    hit["_seq_no"] = 5
    with pytest.raises(c.SafeFailure, match="mixed_document"):
        target.verify([row], 10000)
    hit["_seq_no"] = 4
    source["unexpected_field"] = 1
    with pytest.raises(c.SafeFailure, match="content_or_vector"):
        target.verify([row], 10000)
    source.pop("unexpected_field")
    hit["fields"] = {}
    with pytest.raises(c.SafeFailure, match="root_indexed_presence"):
        target.verify([row], 10000)


@pytest.mark.parametrize("alter", ["stored_root_scaled", "nested_scaled", "unfiltered_root_missing",
                                   "filtered_root_normalized", "stored_values_float32"])
def test_stored_source_vectors_are_checked_separately_from_indexed_direction(alter):
    row = event()
    source = copy.deepcopy(row["after"])
    excluded = set()
    if alter == "stored_root_scaled":
        source["title_embedding"] = vector(0.2)
    elif alter == "nested_scaled":
        source["indexes"][0]["embedding"] = vector(0.4)
    elif alter in ("unfiltered_root_missing", "filtered_root_normalized"):
        source.pop("title_embedding")
        if alter == "filtered_root_normalized":
            excluded = {"title_embedding"}
    elif alter == "stored_values_float32":
        source["title_embedding"] = vector(0.10000000149)
        source["indexes"][0]["embedding"] = vector(0.20000000298)
    doc = {"_index": row["index"], "_id": row["id"], "_version": 10001,
           "_seq_no": 1, "_primary_term": 1, "found": True, "_source": source}
    hit = {key: value for key, value in doc.items() if key not in ("found", "_source")}
    hit["fields"] = {"title_embedding": [vector(1 / 32)]}
    target = object.__new__(c.Target)
    target.source_excludes = {row["index"]: excluded}
    target.call = lambda method, path, **kwargs: {"docs": [doc]} if path.endswith("_mget") else {"hits": {"hits": [hit]}}
    if alter in ("filtered_root_normalized", "stored_values_float32"):
        target.verify([row], 10000)
    else:
        with pytest.raises(c.SafeFailure, match="source_root_missing|content_or_vector_mismatch"):
            target.verify([row], 10000)


def test_vector_comparison_accepts_float32_cosine_normalization_not_direction_change():
    assert c.vector_equal(vector(0.1), vector(1 / 32))
    wrong = vector()
    wrong[0] = -0.1
    assert not c.vector_equal(vector(), wrong)
    assert not c.equal_source({"del_flag": True}, {"del_flag": 1})
    assert c.equal_source({"indexes": [{"metadata": {"embedding": "ordinary metadata"}}]},
                          {"indexes": [{"metadata": {"embedding": "ordinary metadata"}}]})


def test_preflight_missing_or_alias_target_never_creates():
    target = object.__new__(c.Target)
    paths = []
    def call(method, path, **kwargs):
        paths.append((method, path))
        return {"unexpected_physical": {"settings": {"index.uuid": "x"}}}
    target.call = call
    with pytest.raises(c.SafeFailure, match="exact_physical"):
        target.preflight("paas_0")
    assert paths == [("GET", "/paas_0/_settings")]


def test_frozen_log_changes_between_passes_stop(setup):
    args, seal = setup
    seal()
    plan, plan_sha = c.load_plan(args.plan)
    window = c.Window(args.manifest, plan, plan_sha).validate()
    window.file.write_bytes(window.file.read_bytes() + b"changed")
    with pytest.raises(c.SafeFailure, match="frozen_log_changed"):
        list(window.final_events())


def test_all_bulk_ack_then_one_refresh_then_all_ids_verified(setup):
    args, seal = setup
    seal([event(i + 1, ident=str(i)) for i in range(65)])
    args.apply = True
    target = FakeTarget()
    order = []
    target.bulk = lambda rows, payload, base: order.append(("bulk", len(rows)))
    target.refresh = lambda indices: order.append(("refresh", len(indices)))
    target.verify = lambda rows, base: order.append(("verify", len(rows)))
    assert c.consume(args, lambda _: target)["applied_cursor"] == 65
    assert order == [("bulk", 32), ("bulk", 32), ("bulk", 1), ("refresh", 1),
                     ("verify", 32), ("verify", 32), ("verify", 1)]


def test_refresh_failure_never_advances_cursor(setup):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    def fail(_):
        raise c.SafeFailure("refresh_failed")
    target.refresh = fail
    with pytest.raises(c.SafeFailure, match="refresh_failed"):
        c.consume(args, lambda _: target)
    assert c.read_json(args.state)["applied_cursor"] == 0


def test_new_state_cannot_replay_old_upsert_after_delete_tombstone_gc(setup):
    args, seal = setup
    seal([event()])
    args.apply = True
    target = FakeTarget()
    c.consume(args, lambda _: target)
    seal([event(2, "delete")], start_exclusive=1)
    c.consume(args, lambda _: target)
    target.stored.clear()  # Model expiration of all ES delete-version records.
    seal([event()])
    args.state = str(Path(args.state).with_name("replacement_state.json"))
    with pytest.raises(c.SafeFailure, match="other_state_path"):
        c.consume(args, forbidden_factory)
    assert not Path(args.state).exists()


def test_registered_state_loss_is_not_reinitialized_by_initial_cursor(setup):
    args, seal = setup
    seal()
    args.apply = True
    c.consume(args, lambda _: FakeTarget())
    Path(args.state).unlink()
    with pytest.raises(c.SafeFailure, match="registered_state_missing"):
        c.consume(args, forbidden_factory)
    assert not Path(args.state).exists()


def test_old_state_snapshot_cannot_roll_back_registry_cursor(setup):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    c.consume(args, lambda _: target)
    old_state = Path(args.state).read_bytes()
    seal([event(2, "delete")], start_exclusive=1)
    c.consume(args, lambda _: target)
    Path(args.state).write_bytes(old_state)
    # Even the formerly successful old window is rejected; no done early exit.
    seal([event()])
    with pytest.raises(c.SafeFailure, match="registry_ahead_of_state"):
        c.consume(args, forbidden_factory)


@pytest.mark.parametrize("empty", [False, True])
def test_registry_commit_failure_recovers_from_verified_state_without_rewriting(setup, monkeypatch, empty):
    args, seal = setup
    seal([] if empty else [event()])
    args.apply = True
    original_save = c.atomic_save
    registry_path = Path(args.state).with_name("registry.json")
    failed = False
    def fail_final_registry(path, body):
        nonlocal failed
        if Path(path) == registry_path and body.get("last_manifest_sha256") and body.get("pending") is None and not failed:
            failed = True
            raise OSError("simulated durable registry failure")
        original_save(path, body)
    monkeypatch.setattr(c, "atomic_save", fail_final_registry)
    with pytest.raises(OSError):
        c.consume(args, lambda _: FakeTarget())
    state = c.read_json(args.state)
    assert state["pending"] is None and state["last_manifest_sha256"]
    assert c.read_json(registry_path)["pending"]
    report = c.consume(args, forbidden_factory)
    assert report["already_applied"] is True
    registry = c.read_json(registry_path)
    assert registry["pending"] is None and registry["applied_cursor"] == state["applied_cursor"]


def test_registry_pending_prevents_manifest_swap_before_state_pending_write(setup, monkeypatch):
    args, seal = setup
    seal()
    args.apply = True
    target = FakeTarget()
    target.preflight = lambda _: (_ for _ in ()).throw(c.SafeFailure("preflight_failed"))
    with pytest.raises(c.SafeFailure, match="preflight_failed"):
        c.consume(args, lambda _: target)
    assert c.read_json(args.state)["pending"] is None
    changed = event()
    changed["after"]["title"] = "changed window"
    seal([changed])
    with pytest.raises(c.SafeFailure, match="registry_different_pending_window"):
        c.consume(args, forbidden_factory)


def test_pristine_state_registration_failure_can_retry_before_any_es_write(setup, monkeypatch):
    args, seal = setup
    seal()
    args.apply = True
    save = c.atomic_save
    registry = Path(args.state).with_name("registry.json")
    first = True
    def fail_once(path, value):
        nonlocal first
        if Path(path) == registry and first:
            first = False
            raise OSError("register failed")
        save(path, value)
    monkeypatch.setattr(c, "atomic_save", fail_once)
    with pytest.raises(OSError):
        c.consume(args, forbidden_factory)
    assert not registry.exists()
    assert c.read_json(args.state)["applied_cursor"] == 0
    assert c.consume(args, lambda _: FakeTarget())["applied_cursor"] == 1


def test_registry_missing_for_used_state_requires_manual_handoff(setup):
    args, seal = setup
    seal()
    args.apply = True
    c.consume(args, lambda _: FakeTarget())
    Path(args.state).with_name("registry.json").unlink()
    with pytest.raises(c.SafeFailure, match="registry_missing_for_existing_state"):
        c.consume(args, forbidden_factory)
