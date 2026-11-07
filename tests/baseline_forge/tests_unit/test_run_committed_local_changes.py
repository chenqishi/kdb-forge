"""Offline orchestration gates around the real consumer; fake targets only."""
import gzip
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_committed_local_changes.py"
spec = importlib.util.spec_from_file_location("local_change_runner", SCRIPT)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
c = r.consumer


@pytest.fixture
def setup(tmp_path, monkeypatch):
    logs = tmp_path / "committed"
    logs.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    plan_path, config, lease = [control / f"{name}.json" for name in ("plan", "config", "lease")]
    plan_path.write_bytes(c.encoded({"selected_count": 86, "selected": [
        {"source_index": f"{p}_{i}", "provider": p}
        for p, count in (("paas", 5), ("serverless", 81)) for i in range(count)]}))
    config.write_bytes(c.encoded({"providers": {p: {"host": f"https://{p}.invalid"}
                                               for p in ("paas", "serverless")}}))
    lease.write_bytes(c.encoded({"provider": "serverless", "status": "released",
                                "indices": [f"serverless_{i}" for i in range(81)]}))
    monkeypatch.setattr(c, "canonical_paths", lambda p, e: (control / "canonical.lock", control / "registry.json"))
    args = SimpleNamespace(manifest_dir=str(logs), manifest_glob="**/manifest.json",
                           state=str(control / "state.json"), health=None, plan=str(plan_path),
                           config=str(config), lease=str(lease), initial_cursor=0, apply=False,
                           watch=False, poll_seconds=2, retry_seconds=5)

    def seal(start=0, end=1, tag=None, status="committed", title="private source", op="upsert"):
        directory = logs / (tag or f"{start:06d}-{end:06d}")
        directory.mkdir(exist_ok=True)
        event = {"stream_id": "runner-test", "provider": "paas", "index": "paas_0",
                 "id": "id", "cursor": end, "op": op}
        if op == "upsert":
            event["after"] = {"title": title, "del_flag": 0}
        data = b"" if start == end else c.encoded(event) + b"\n"
        payload = gzip.compress(data, mtime=0)
        (directory / "events.gz").write_bytes(payload)
        manifest = {"contract": c.CONTRACT, "status": status, "stream_id": "runner-test",
                    "version_base": 10000, "start_exclusive": start, "end_inclusive": end,
                    "records": int(end > start), "approved_plan_sha256": c.sha(plan_path.read_bytes()),
                    "file": "events.gz", "sha256": c.sha(payload)}
        path = directory / "manifest.json"
        path.write_bytes(c.encoded(manifest))
        return path
    return args, seal, control


class FakeTarget:
    def __init__(self):
        self.cursors = []
        self.fail_count = 0

    def identity(self, index):
        return "fixed-uuid"

    preflight = identity

    def bulk(self, events, payload, version_base):
        self.cursors.extend(e["cursor"] for e in events)
        if self.fail_count:
            self.fail_count -= 1
            raise c.SafeFailure("simulated_partial_bulk_failure")

    def refresh(self, indices):
        pass

    def verify(self, events, version_base):
        pass


def fake_consume(target):
    return lambda args: c.consume(args, target_factory=lambda config: target)


def forbid(_):
    raise AssertionError("consumer must not be called")


def test_default_dry_run_once_no_network_state_registry_or_health(setup, monkeypatch):
    args, seal, control = setup
    seal()
    monkeypatch.setattr(c, "Target", lambda _: (_ for _ in ()).throw(AssertionError("network")))
    # Explicit factory catches network even though consume's default is bound.
    runner = r.Runner(args, lambda a: c.consume(a, target_factory=forbid))
    emitted = []
    report = runner.run(emitted.append, sleep=lambda _: pytest.fail("dry-run polled"))
    assert len(emitted) == 1 and report["status"] == "dry_run_validated"
    assert report["applied_cursor"] == 0 and report["exportable_windows"] == 1
    assert report["freshness_proven"] is False
    assert not Path(args.state).exists() and not runner.health_path.exists()
    assert not (control / "registry.json").exists() and not list(control.glob("*.lock"))


def test_watch_requires_explicit_apply(setup):
    args, _, _ = setup
    args.watch = True
    with pytest.raises(c.SafeFailure, match="watch_requires_apply"):
        r.Runner(args)


def test_failure_retries_same_local_window_before_later_one(setup):
    args, seal, control = setup
    seal(0, 1)
    seal(1, 2)
    args.apply = args.watch = True
    target = FakeTarget()
    target.fail_count = 1
    reports, waits = [], []
    r.Runner(args, fake_consume(target)).run(reports.append, sleep=waits.append, max_ticks=3)
    assert target.cursors == [1, 1, 2]
    assert [x["status"] for x in reports] == ["failed", "applied", "applied"]
    assert [x["applied_cursor"] for x in reports] == [0, 1, 2]
    assert waits == [5]
    health = c.read_json(Path(args.state).with_suffix(".health.json"))
    assert health["applied_windows"] == 2 and health["exportable_windows"] == 0
    assert health["last_success_at"] and health["failure_reason"] is None
    assert health["freshness_proven"] is False


def test_restart_selects_durable_pending_before_future_window(setup):
    args, seal, _ = setup
    seal(0, 1)
    seal(1, 2)
    args.apply = True
    target = FakeTarget()
    target.fail_count = 1
    first = r.Runner(args, fake_consume(target))
    assert first.tick()["status"] == "failed"
    first.health_path.unlink()  # Registry/state pending remains authoritative.
    resumed = r.Runner(args, fake_consume(target))
    assert resumed.tick()["applied_cursor"] == 1
    assert target.cursors == [1, 1]


def test_gap_waits_without_network_or_cursor_jump(setup):
    args, seal, _ = setup
    seal(5, 6)
    args.apply = True
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "waiting_for_gap" and report["next_available_start"] == 5
    assert report["applied_cursor"] == 0 and not Path(args.state).exists()


def test_pending_missing_manifest_waits_instead_of_skipping(setup):
    args, seal, _ = setup
    path = seal(0, 1)
    seal(1, 2)
    args.apply = True
    target = FakeTarget()
    target.fail_count = 1
    assert r.Runner(args, fake_consume(target)).tick()["status"] == "failed"
    path.rename(path.with_suffix(".retained"))
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "waiting_for_pending_manifest"
    assert report["applied_cursor"] == 0


@pytest.mark.parametrize("mode", ["same_cursor", "overlap"])
def test_conflicting_closed_windows_rejected_before_target(setup, mode):
    args, seal, _ = setup
    if mode == "same_cursor":
        seal(0, 1, tag="one")
        seal(0, 1, tag="other", title="different")
    else:
        seal(0, 5)
        seal(3, 8)
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "failed"
    assert report["failure_reason"] in ("conflicting_cursor_manifest_sha", "overlapping_closed_windows")


def test_uncommitted_and_temporary_manifests_are_not_consumed(setup):
    args, seal, _ = setup
    seal(0, 1, status="writing")
    temporary = seal(1, 2)
    temporary.rename(temporary.with_suffix(".json.tmp"))
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "waiting_for_manifest"
    assert report["committed_windows"] == 0 and report["ignored_uncommitted"] == 1


def test_retained_nonempty_adjacent_empty_and_next_window_do_not_block(setup):
    args, seal, _ = setup
    seal(0, 1)
    seal(1, 1)
    seal(1, 2)
    args.apply = True
    target = FakeTarget()
    runner = r.Runner(args, fake_consume(target))
    first, second, idle = runner.tick(), runner.tick(), runner.tick()
    assert [first["applied_cursor"], second["applied_cursor"]] == [1, 2]
    assert target.cursors == [1, 2]
    assert first["applied_windows"] == 2 and first["exportable_windows"] == 1
    assert second["applied_windows"] == 3 and second["exportable_windows"] == 0
    assert idle["status"] == "waiting_for_manifest"


def test_empty_only_dry_run_has_no_network_or_state_side_effects(setup):
    args, seal, control = setup
    seal(0, 0)
    runner = r.Runner(args, forbid)
    report = runner.tick()
    assert report["status"] == "waiting_for_manifest" and report["applied_cursor"] == 0
    assert report["committed_windows"] == 1 and report["exportable_windows"] == 0
    assert not Path(args.state).exists() and not runner.health_path.exists()
    assert not (control / "registry.json").exists()


def test_consecutive_different_empty_manifests_at_same_cursor_are_legal(setup):
    args, seal, _ = setup
    seal(0, 1)
    seal(1, 1, tag="empty-one")
    second = seal(1, 1, tag="empty-two")
    body = c.read_json(second)
    (second.parent / "events.gz").rename(second.parent / "second-empty.gz")
    body["file"] = "second-empty.gz"
    second.write_bytes(c.encoded(body))
    seal(1, 2)
    args.apply = True
    target = FakeTarget()
    runner = r.Runner(args, fake_consume(target))
    assert runner.tick()["applied_cursor"] == 1
    report = runner.tick()
    assert report["applied_cursor"] == 2 and report["applied_windows"] == 4
    assert target.cursors == [1, 2]


def test_health_pinned_empty_recovers_exact_sha_once_without_oscillating(setup):
    args, seal, _ = setup
    args.initial_cursor = 1
    first = seal(1, 1, tag="empty-one")
    second = seal(1, 1, tag="empty-two")
    body = c.read_json(second)
    body["producer_note"] = "distinct but legal empty manifest"
    second.write_bytes(c.encoded(body))
    before = r.Runner(args, forbid)
    health = before.tick()
    pinned_sha = c.sha(first.read_bytes())
    health["retry_window"] = {"manifest_sha256": pinned_sha, "start_exclusive": 1, "end_inclusive": 1}
    before.health_path.write_bytes(c.encoded(health))
    args.apply = True
    runner = r.Runner(args, lambda a: c.consume(a, target_factory=forbid))
    assert runner.tick()["status"] == "recovered"
    assert c.read_json(args.state)["last_manifest_sha256"] == pinned_sha
    assert runner.tick()["status"] == "waiting_for_manifest"
    assert c.read_json(args.state)["last_manifest_sha256"] == pinned_sha


def test_failed_sha_is_pinned_in_health_even_before_consumer_state_exists(setup):
    args, seal, _ = setup
    path = seal()
    gzip_path = path.parent / "events.gz"
    gzip_path.write_bytes(gzip_path.read_bytes() + b"corrupt")
    args.apply = True
    report = r.Runner(args, lambda a: c.consume(a, target_factory=forbid)).tick()
    assert report["status"] == "failed" and report["failure_reason"] == "compressed_log_sha_mismatch"
    assert not Path(args.state).exists()
    # Replacing the committed window with a newly signed payload is rejected
    # after restart even though no target write/state initialization occurred.
    seal(title="replacement")
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "failed" and report["failure_reason"] == "pending_manifest_sha_conflict"


def test_runner_preserves_real_consumer_registry_other_state_rejection(setup):
    args, seal, _ = setup
    seal()
    args.apply = True
    assert r.Runner(args, fake_consume(FakeTarget())).tick()["status"] == "applied"
    original_state = Path(args.state).read_bytes()
    args.state = str(Path(args.state).with_name("state_b.json"))
    report = r.Runner(args, fake_consume(FakeTarget())).tick()
    assert report["status"] == "failed" and report["failure_reason"] == "canonical_registry_other_state_path"
    assert not Path(args.state).exists()
    assert Path(args.state).with_name("state.json").read_bytes() == original_state


def test_runner_rejects_missing_registered_state_without_reinitialization(setup):
    args, seal, _ = setup
    seal()
    args.apply = True
    assert r.Runner(args, fake_consume(FakeTarget())).tick()["status"] == "applied"
    Path(args.state).unlink()
    report = r.Runner(args, forbid).tick()
    assert report["status"] == "failed" and report["failure_reason"] == "registered_state_missing"


def test_registry_final_commit_failure_recovered_before_next_window(setup, monkeypatch):
    args, seal, control = setup
    seal(0, 1)
    seal(1, 2)
    args.apply = True
    target = FakeTarget()
    original_save, failed = c.atomic_save, False
    def fail_registry_once(path, body):
        nonlocal failed
        if Path(path) == control / "registry.json" and body.get("last_manifest_sha256") and not body.get("pending") and not failed:
            failed = True
            raise OSError("registry commit failure")
        original_save(path, body)
    monkeypatch.setattr(c, "atomic_save", fail_registry_once)
    runner = r.Runner(args, fake_consume(target))
    assert runner.tick()["status"] == "failed"
    report = runner.tick()
    assert report["status"] == "recovered" and report["applied_cursor"] == 1
    assert target.cursors == [1]
    assert c.read_json(control / "registry.json")["applied_cursor"] == 1
    assert runner.tick()["status"] == "applied" and target.cursors == [1, 2]


def test_failure_report_is_sanitized(setup):
    args, seal, _ = setup
    seal()
    def fail(_):
        raise RuntimeError("password and PRIVATE SOURCE CONTENT")
    report = r.Runner(args, fail).tick()
    assert report["failure_reason"] == "local_RuntimeError"
    assert b"PRIVATE" not in c.encoded(report)


@pytest.mark.parametrize("destination", ["config", "state", "registry", "producer"])
def test_health_cannot_overwrite_control_files_or_committed_logs(setup, destination):
    args, seal, control = setup
    path = seal()
    args.health = {"config": args.config, "state": args.state,
                   "registry": str(control / "registry.json"), "producer": str(path)}[destination]
    with pytest.raises(c.SafeFailure, match="replace_state|overwrites_control_file|inside_producer"):
        r.Runner(args)
