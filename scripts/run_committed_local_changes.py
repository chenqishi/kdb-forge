#!/usr/bin/env python3
"""Watch sealed local manifests; never queries source ES or creates source CDC.

Default: one offline inspection, report to stdout, no health/state writes.
--apply enables target consumption; --apply --watch enables foreground polling.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_committed_local_changes as consumer

HEALTH_CONTRACT = "es8-local-runner-health-v1"


def now():
    return datetime.now(timezone.utc).isoformat()


def failure_reason(exc):
    # Do not emit paths, request bodies, exception response text or credentials.
    if isinstance(exc, consumer.SafeFailure):
        reason = str(exc)
        if reason.replace("_", "").isalnum():
            return reason
    return "local_" + type(exc).__name__


def scan_windows(directory, pattern, plan, plan_sha):
    root = Path(directory).resolve()
    consumer.require(root.is_dir(), "manifest_directory_missing")
    consumer.require(not Path(pattern).is_absolute() and ".." not in Path(pattern).parts,
                     "invalid_manifest_glob")
    windows, ignored, by_range, empty_shas = [], 0, {}, set()
    stream = None
    for path in sorted(root.glob(pattern)):
        if not path.is_file() or path.name.endswith((".tmp", ".partial")):
            continue
        consumer.require(not path.is_symlink() and path.resolve().is_relative_to(root), "manifest_outside_directory")
        body = consumer.read_json(path)
        consumer.require(isinstance(body, dict), "manifest_not_object")
        if body.get("status") != "committed":
            ignored += 1
            continue
        # Reuse the consumer's metadata/path checks. Full compressed SHA and
        # per-event validation happen in consume() before any target request.
        window = consumer.Window(path, plan, plan_sha)
        meta = window.m
        consumer.require((meta["records"] == 0) == (meta["start_exclusive"] == meta["end_inclusive"]),
                         "empty_window_bounds_mismatch")
        identity = (meta["stream_id"], meta["version_base"])
        consumer.require(stream is None or identity == stream, "mixed_stream_or_version_base")
        stream = identity
        interval = (meta["start_exclusive"], meta["end_inclusive"])
        if interval[0] == interval[1]:
            # Consecutive no-change exports may seal different empty files at
            # the same cursor. They contain no conflicting event versions.
            if window.manifest_sha not in empty_shas:
                empty_shas.add(window.manifest_sha)
                windows.append(window)
            continue
        previous = by_range.get(interval)
        consumer.require(previous is None or previous.manifest_sha == window.manifest_sha,
                         "conflicting_cursor_manifest_sha")
        if previous is None:
            by_range[interval] = window
            windows.append(window)
    windows.sort(key=lambda w: (w.m["start_exclusive"], w.m["end_inclusive"], w.manifest_sha))
    end = None
    for window in windows:
        start = window.m["start_exclusive"]
        consumer.require(end is None or start >= end, "overlapping_closed_windows")
        end = window.m["end_inclusive"]
    return windows, ignored


def pending_identity(window):
    return {"manifest_sha256": window.manifest_sha,
            "start_exclusive": window.m["start_exclusive"], "end_inclusive": window.m["end_inclusive"]}


class Runner:
    def __init__(self, args, consume_fn=consumer.consume):
        self.args, self.consume_fn = args, consume_fn
        self.retry = None
        self.retry_loaded = False
        self.window_ends = []
        self.state_path = Path(args.state).resolve()
        self.health_path = Path(args.health).resolve() if args.health else self.state_path.with_suffix(".health.json")
        consumer.require(self.health_path != self.state_path, "health_must_not_replace_state")
        producer_dir = Path(args.manifest_dir).resolve()
        consumer.require(not self.health_path.is_relative_to(producer_dir)
                         and not self.state_path.is_relative_to(producer_dir), "consumer_outputs_inside_producer_directory")
        plan, _ = consumer.load_plan(args.plan)
        endpoints = consumer.endpoint_binding(consumer.read_json(args.config), plan)
        lock, registry = consumer.canonical_paths(plan, endpoints)
        protected = {Path(p).resolve() for p in (args.plan, args.config, args.lease, lock, registry,
                                                 lock.with_suffix(".runner.lock"))}
        consumer.require(self.health_path not in protected and self.state_path not in protected,
                         "consumer_output_overwrites_control_file")
        self.previous_health = consumer.read_json(self.health_path) if self.health_path.exists() else {}
        consumer.require(not self.previous_health or self.previous_health.get("health_contract") == HEALTH_CONTRACT,
                         "health_file_belongs_to_other_tool")
        self.retry = self.previous_health.get("retry_window")
        consumer.require(not args.watch or args.apply, "watch_requires_apply")
        consumer.require(math.isfinite(args.poll_seconds) and 1 <= args.poll_seconds <= 3600,
                         "invalid_poll_interval")
        consumer.require(math.isfinite(args.retry_seconds) and 5 <= args.retry_seconds <= 3600,
                         "invalid_retry_interval")

    def state_summary(self):
        state = consumer.read_json(self.state_path) if self.state_path.exists() else {}
        cursor = state.get("applied_cursor", self.args.initial_cursor)
        consumer.require(consumer.integer(cursor) and cursor >= 0, "explicit_initial_cursor_or_valid_state_required")
        return state, cursor

    def inspect(self):
        plan, plan_sha = consumer.load_plan(self.args.plan)
        endpoints = consumer.endpoint_binding(consumer.read_json(self.args.config), plan)
        lock, registry_path = consumer.canonical_paths(plan, endpoints)
        windows, ignored = scan_windows(self.args.manifest_dir, self.args.manifest_glob, plan, plan_sha)
        self.window_ends = [w.m["end_inclusive"] for w in windows]
        state, cursor = self.state_summary()
        registry_disk = consumer.read_json(registry_path) if registry_path.exists() else {}
        old_binding = (state or registry_disk).get("bindings") or {}
        if windows:
            stream_id, version_base = windows[0].m["stream_id"], windows[0].m["version_base"]
        else:
            stream_id, version_base = old_binding.get("stream_id"), old_binding.get("version_base")
        bindings = {"stream_id": stream_id, "version_base": version_base,
                    "approved_plan_sha256": plan_sha, "target_endpoint_sha256": endpoints}
        if state:
            consumer.require(state.get("contract") == consumer.CONTRACT and state.get("bindings") == bindings,
                             "state_binding_mismatch")
        else:
            state = {"contract": consumer.CONTRACT, "bindings": bindings, "applied_cursor": cursor,
                     "pending": None, "index_uuids": {}}
        # Read-only even in apply mode. Actual registration/repair is left to
        # consume(), under its canonical lock and existing lease guard.
        registry = consumer.register_state(registry_path, self.state_path, state, bindings, persist=False)
        repairing_registry = bool(registry_disk and (
            registry_disk.get("applied_cursor") != registry.get("applied_cursor")
            or registry_disk.get("last_manifest_sha256") != registry.get("last_manifest_sha256")))
        pending = registry_disk.get("pending") if repairing_registry else state.get("pending") or registry.get("pending")
        if state.get("pending") and registry.get("pending"):
            consumer.require(state["pending"] == registry["pending"], "state_registry_pending_mismatch")
        context = consumer.sha(consumer.encoded({"bindings": bindings, "state_path": str(self.state_path)}))
        if not self.retry_loaded:
            self.retry_loaded = True
            self.retry = self.previous_health.get("retry_window") if self.previous_health.get("context_sha256") == context else None
        if self.retry:
            retry_end = self.retry.get("end_inclusive", -1)
            completed_exactly = (retry_end == cursor and not state.get("pending")
                                 and not registry.get("pending") and not repairing_registry
                                 and state.get("last_manifest_sha256") == self.retry.get("manifest_sha256"))
            if retry_end < cursor or completed_exactly:
                self.retry = None
        if not pending:
            pending = self.retry
        report = {"health_contract": HEALTH_CONTRACT, "mode": "apply" if self.args.apply else "dry_run", "at": now(),
                  "context_sha256": context, "status": "waiting_for_manifest", "applied_cursor": cursor,
                  "applied_windows": sum(w.m["end_inclusive"] <= cursor for w in windows),
                  "exportable_windows": sum(w.m["end_inclusive"] > cursor for w in windows),
                  "committed_windows": len(windows), "ignored_uncommitted": ignored,
                  "window_count_basis": "committed_manifest_metadata_full_gzip_validation_before_apply",
                  "last_success_at": state.get("last_applied_at"), "failure_reason": None,
                  "retry_window": pending, "registry_recovery_required": repairing_registry, "freshness_proven": False}
        selected = None
        if pending:
            consumer.require(pending.get("end_inclusive") == cursor if repairing_registry
                             else pending.get("start_exclusive") == cursor, "pending_window_cursor_mismatch")
            selected = next((w for w in windows if w.manifest_sha == pending.get("manifest_sha256")), None)
            if selected is None:
                consumer.require(pending["start_exclusive"] == pending["end_inclusive"]
                                 or not any(w.m["start_exclusive"] == pending["start_exclusive"]
                                         and w.m["end_inclusive"] == pending["end_inclusive"] for w in windows),
                                 "pending_manifest_sha_conflict")
                report["status"] = "waiting_for_pending_manifest"
            else:
                consumer.require(pending_identity(selected) == pending, "pending_manifest_bounds_mismatch")
        else:
            remaining = [w for w in windows if w.m["end_inclusive"] > cursor]
            if remaining:
                selected = remaining[0]
                consumer.require(selected.m["start_exclusive"] >= cursor, "applied_cursor_inside_window")
                if selected.m["start_exclusive"] > cursor:
                    report.update(status="waiting_for_gap", next_available_start=selected.m["start_exclusive"])
                    selected = None
        if selected:
            report.update(status="ready", selected_window=pending_identity(selected))
        return report, selected, lock

    def tick(self):
        report = {"health_contract": HEALTH_CONTRACT, "mode": "apply" if self.args.apply else "dry_run", "at": now(),
                  "status": "failed", "applied_cursor": None, "applied_windows": None,
                  "exportable_windows": None, "last_success_at": None, "failure_reason": None,
                  "retry_window": self.retry, "context_sha256": self.previous_health.get("context_sha256"),
                  "freshness_proven": False}
        try:
            report, selected, _ = self.inspect()
            if selected:
                self.retry = pending_identity(selected)
                report["retry_window"] = self.retry
                consume_args = SimpleNamespace(manifest=str(selected.path), state=str(self.state_path),
                    plan=self.args.plan, config=self.args.config, lease=self.args.lease,
                    initial_cursor=self.args.initial_cursor, apply=self.args.apply)
                result = self.consume_fn(consume_args)
                if self.args.apply:
                    # Re-read durable state instead of treating a return value
                    # alone as a committed cursor.
                    state, cursor = self.state_summary()
                    consumer.require(cursor == selected.m["end_inclusive"]
                                     and result.get("applied_cursor") == cursor, "consumer_did_not_commit_window")
                    self.retry = None
                    advanced = cursor > report["applied_cursor"]
                    report.update(status="applied" if advanced else "recovered", applied_cursor=cursor, retry_window=None,
                                  applied_windows=sum(end <= cursor for end in self.window_ends),
                                  exportable_windows=sum(end > cursor for end in self.window_ends),
                                  registry_recovery_required=False,
                                  last_success_at=state.get("last_applied_at"))
                else:
                    self.retry = None
                    report.update(status="dry_run_validated", retry_window=None)
        except Exception as exc:
            report.update(status="failed", failure_reason=failure_reason(exc), retry_window=self.retry)
            try:
                state, cursor = self.state_summary()
                report.update(applied_cursor=cursor, last_success_at=state.get("last_applied_at"))
            except Exception:
                pass
        if self.args.apply:
            # Health is observability, never the authority to advance a cursor.
            consumer.atomic_save(self.health_path, report)
            self.previous_health = report
        return report

    def run(self, emit, sleep=time.sleep, max_ticks=None):
        # Separate process lock, so it cannot deadlock consume()'s per-window
        # canonical lock. It prevents two watchers from racing on health/retry.
        plan, _ = consumer.load_plan(self.args.plan)
        endpoints = consumer.endpoint_binding(consumer.read_json(self.args.config), plan)
        lock, _ = consumer.canonical_paths(plan, endpoints)
        guard = consumer.exclusive_lock(lock.with_suffix(".runner.lock")) if self.args.apply else nullcontext()
        with guard:
            ticks = 0
            while True:
                report = self.tick()
                emit(report)
                ticks += 1
                if not self.args.watch or max_ticks is not None and ticks >= max_ticks:
                    return report
                if report["status"] in ("applied", "recovered"):
                    continue
                sleep(self.args.retry_seconds if report["status"] == "failed" else self.args.poll_seconds)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest-dir", required=True)
    result.add_argument("--manifest-glob", default="**/manifest.json")
    result.add_argument("--state", required=True)
    result.add_argument("--health", help="Default: state path with .health.json suffix; written only with --apply")
    result.add_argument("--plan", default=consumer.DEFAULT_PLAN)
    result.add_argument("--config", default="config/config_es_runtime.local.json")
    result.add_argument("--lease", default=consumer.DEFAULT_LEASE)
    result.add_argument("--initial-cursor", type=int)
    result.add_argument("--apply", action="store_true")
    result.add_argument("--watch", action="store_true", help="Foreground polling; requires --apply")
    result.add_argument("--poll-seconds", type=float, default=15)
    result.add_argument("--retry-seconds", type=float, default=30)
    return result


def main():
    try:
        runner = Runner(parser().parse_args())
        result = runner.run(lambda report: print(consumer.encoded(report).decode(), flush=True))
        return 2 if result["status"] == "failed" else 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(consumer.encoded({"status": "failed", "failure_reason": failure_reason(exc),
                                "freshness_proven": False}).decode(), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
