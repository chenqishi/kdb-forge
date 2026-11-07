"""Offline safety gates for local root-vector restoration; never contacts ES."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "restore_local_root_vectors.py"
spec = importlib.util.spec_from_file_location("restore_local_root_vectors", SCRIPT)
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


def vec(value=0.01):
    return [value] * 1024


def sample():
    local = {"_id": "same-id", "_source": {"title": "title", "content": "body",
              "title_embedding": vec(), "content_embedding": vec(0.02)}}
    current = {"_id": "same-id", "found": True, "_seq_no": 7, "_primary_term": 2,
               "_source": {"title": "title", "content": "body", "update_time": "newer"}}
    indexed = {"_id": "same-id", "_seq_no": 7, "_primary_term": 2, "fields": {}}
    return local, current, indexed


def test_patch_is_root_only_and_cas_without_upsert():
    update, reason = restore.decide(*sample())
    assert reason is None
    parts = list(restore.bulk_parts("mercado", [update]))
    action, body = [json.loads(line) for line in parts[0][1].splitlines()]
    assert action == {"update": {"_index": "mercado", "_id": "same-id",
                                  "if_seq_no": 7, "if_primary_term": 2}}
    assert set(body) == {"doc"}
    assert set(body["doc"]) == set(restore.ROOTS)


def test_preserves_existing_other_root_despite_source_exclusion():
    local, current, indexed = sample()
    indexed["fields"]["title_embedding"] = [vec(0.9)]
    update, reason = restore.decide(local, current, indexed)
    assert reason is None
    assert update["added"] == ["content_embedding"]
    assert update["doc"]["title_embedding"] == vec(0.9)


@pytest.mark.parametrize("change,expected", [
    ("missing", "missing_id"), ("stale", "version_not_visible"),
    ("title", "content_changed"), ("content", "content_changed"),
    ("missing_null", "content_changed"), ("invalid_current", "invalid_current_vector"),
])
def test_guards(change, expected):
    local, current, indexed = sample()
    if change == "missing":
        current["found"] = False
    elif change == "stale":
        indexed["_seq_no"] = 6
    elif change in ("title", "content"):
        current["_source"][change] = "changed"
    elif change == "missing_null":
        current["_source"].pop("title")
        local["_source"]["title"] = None
    else:
        indexed["fields"]["title_embedding"] = [[0.0] * 1024]
    assert restore.decide(local, current, indexed) == (None, expected)


@pytest.mark.parametrize("value", [[], [1.0], [0.0] * 1024, [float("nan")] * 1024,
                                   [float("inf")] * 1024, [True] * 1024])
def test_reject_invalid_vectors(value):
    assert not restore.valid_vector(value)


def test_partial_bulk_is_failure_even_when_first_item_succeeded():
    update, _ = restore.decide(*sample())
    second = {**update, "_id": "conflict-id"}

    class FakeTarget:
        def call(self, *args, **kwargs):
            return {"errors": True, "items": [
                {"update": {"_index": "mercado", "_id": "same-id", "status": 200, "result": "updated"}},
                {"update": {"_index": "mercado", "_id": "conflict-id", "status": 409,
                            "error": {"reason": "PRIVATE TEXT MUST NOT ESCAPE"}}},
            ]}

    with pytest.raises(restore.SafeFailure) as caught:
        restore.apply_batch(FakeTarget(), "mercado", [update, second])
    assert "409" in str(caught.value)
    assert "PRIVATE" not in str(caught.value)


def test_bulk_budgets_and_existing_vectors_skip():
    update, _ = restore.decide(*sample())
    parts = list(restore.bulk_parts("mercado", [{**update, "_id": str(n)} for n in range(65)]))
    assert sum(len(records) for records, _ in parts) == 65
    assert all(len(records) <= 32 and len(payload) <= 2 * 1024 * 1024 for records, payload in parts)
    local, current, indexed = sample()
    indexed["fields"] = {f: [local["_source"][f]] for f in restore.ROOTS}
    assert restore.decide(local, current, indexed)[1] == "already_present_or_no_backup_vector"


def test_incremental_override_and_new_id(tmp_path):
    import gzip
    path = tmp_path / "dump.gz"
    records = [{"_id": "old", "_source": {"title": "before"}}]
    with gzip.open(path, "wt") as f:
        f.write(json.dumps(records[0]) + "\n")
    overrides = {"old": {"_id": "old", "_source": {"title": "after"}},
                 "new": {"_id": "new", "_source": {"title": "new"}}}
    assert list(restore.merged_records(path, overrides)) == [overrides["old"], overrides["new"]]


class MemoryTarget:
    def __init__(self, records, partial=False):
        import copy
        self.docs = {str(r["_id"]): {"_source": {k: v for k, v in copy.deepcopy(r["_source"]).items()
                                              if k not in restore.ROOTS}, "seq": 1}
                     for r in records}
        self.mutations = []
        self.partial = partial

    def preflight(self, index):
        return {"source_excludes": list(restore.ROOTS)}

    def counts(self, index):
        return {"docs": len(self.docs), **{f: sum(f in d["_source"] for d in self.docs.values())
                                          for f in restore.ROOTS}}

    def read(self, index, ids):
        current, indexed = {}, {}
        for ident in ids:
            d = self.docs[ident]
            common = {"_id": ident, "_seq_no": d["seq"], "_primary_term": 1}
            current[ident] = {**common, "found": True,
                              "_source": {k: v for k, v in d["_source"].items() if k not in restore.ROOTS}}
            indexed[ident] = {**common, "fields": {f: [d["_source"][f]] for f in restore.ROOTS
                                                   if f in d["_source"]}}
        return current, indexed

    def call(self, method, path, **kwargs):
        self.mutations.append(path)
        if path.endswith("/_refresh"):
            return {"_shards": {"failed": 0}}
        assert path == "/_bulk"
        payload = kwargs["data"]
        if kwargs.get("headers", {}).get("Content-Encoding") == "gzip":
            import gzip
            payload = gzip.decompress(payload)
        lines = [json.loads(line) for line in payload.splitlines()]
        items = []
        fail = self.partial
        self.partial = False
        for position in range(0, len(lines), 2):
            action, body = lines[position]["update"], lines[position + 1]
            ident = action["_id"]
            assert action["if_seq_no"] == self.docs[ident]["seq"]
            assert action["if_primary_term"] == 1
            assert set(body) == {"doc"} and set(body["doc"]) <= set(restore.ROOTS)
            result = {"_id": ident, "_index": action["_index"]}
            if fail and position > 0:
                result.update(status=409, error={"reason": "PRIVATE conflict details"})
            else:
                self.docs[ident]["_source"].update(body["doc"])
                self.docs[ident]["seq"] += 1
                result.update(status=200, result="updated")
            items.append({"update": result})
        return {"errors": fail, "items": items}


def setup_run(tmp_path, monkeypatch, count=2, partial=False, apply=True, limit=None):
    import argparse
    import gzip
    records = []
    for n in range(count):
        row = sample()[0]
        row["_id"] = str(n)
        row["_source"]["nested_kept"] = [{"text": "preserve"}]
        records.append(row)
    dump = tmp_path / "baseline.gz"
    with gzip.open(dump, "wt") as f:
        for row in records:
            f.write(json.dumps(row) + "\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"providers": {"serverless": {"host": "http://fake"}}}))
    sha = restore.file_sha(dump)
    inputs = (["mercado"], {"mercado": {"dump_file": str(dump)}},
              {"mercado": {"file": str(dump), "sha256": sha}}, {"mercado": {}}, {"sha": sha})
    monkeypatch.setattr(restore, "load_inputs", lambda args: inputs)
    target = MemoryTarget(records, partial)
    monkeypatch.setattr(restore, "Target", lambda endpoint: target)
    args = argparse.Namespace(target_config=str(config), state=str(tmp_path / "state.json"),
                              apply=apply, resume=False, limit=limit)
    return args, target


def test_dry_run_no_mutations_and_limit_resume(tmp_path, monkeypatch):
    args, target = setup_run(tmp_path, monkeypatch, count=3, apply=False, limit=1)
    assert restore.run(args) == 0
    state = json.loads(Path(args.state).read_text())
    assert state["indices"]["mercado"]["offset"] == 1
    assert state["status"] == "limited"
    assert target.mutations == []
    args.resume, args.limit = True, None
    assert restore.run(args) == 0
    state = json.loads(Path(args.state).read_text())
    assert state["indices"]["mercado"]["offset"] == 3
    assert state["indices"]["mercado"]["counters"]["would_update"] == 3
    assert target.mutations == []


@pytest.mark.parametrize("bulk_gzip", [False, True])
def test_partial_failure_does_not_checkpoint_failed_batch_and_resume_is_safe(tmp_path, monkeypatch, bulk_gzip):
    args, target = setup_run(tmp_path, monkeypatch, partial=True)
    args.bulk_gzip = bulk_gzip
    with pytest.raises(restore.SafeFailure):
        restore.run(args)
    state = json.loads(Path(args.state).read_text())
    assert state["status"] == "failed"
    assert state["indices"]["mercado"]["offset"] == 0
    assert state["indices"]["mercado"]["counters"] == {}
    assert "PRIVATE" not in Path(args.state).read_text()
    assert target.counts("mercado")["title_embedding"] == 1
    args.resume = True
    assert restore.run(args) == 0
    state = json.loads(Path(args.state).read_text())
    assert state["status"] == "complete"
    assert state["indices"]["mercado"]["offset"] == 2
    assert target.counts("mercado") == {"docs": 2, "title_embedding": 2, "content_embedding": 2}
    assert all(d["_source"]["nested_kept"] == [{"text": "preserve"}] for d in target.docs.values())
    assert all(r["passed"] for r in state["indices"]["mercado"]["sample_verification"])


def test_resume_after_ack_reconstructs_verification_samples(tmp_path, monkeypatch):
    args, target = setup_run(tmp_path, monkeypatch, count=2, limit=1)
    assert restore.run(args) == 0
    first = json.loads(Path(args.state).read_text())
    assert first["indices"]["mercado"]["verification_anchors"][0]["id"] == "0"
    args.resume, args.limit = True, None
    assert restore.run(args) == 0
    final = json.loads(Path(args.state).read_text())
    assert {r["id"] for r in final["indices"]["mercado"]["sample_verification"]} == {"0", "1"}
    assert all(r["passed"] for r in final["indices"]["mercado"]["sample_verification"])


def test_reject_source_filter_that_would_erase_unrelated_indexed_fields():
    target = object.__new__(restore.Target)
    mapping = {"mercado": {"mappings": {
        "_source": {"excludes": ["title_embedding", "indexes.embedding"]},
        "properties": {f: {"type": "dense_vector", "dims": 1024, "index": True}
                       for f in restore.ROOTS},
    }}}
    target.call = lambda *a, **k: mapping
    with pytest.raises(restore.SafeFailure, match="other_than_roots"):
        target.preflight("mercado")


def test_gzip_transport_decompresses_to_identical_bulk_and_can_resume_same_fingerprint(tmp_path, monkeypatch):
    import gzip
    update, _ = restore.decide(*sample())

    class Capture:
        def __init__(self):
            self.calls = []

        def call(self, method, path, **kwargs):
            self.calls.append((method, path, kwargs))
            return {"errors": False, "items": [{"update": {
                "_index": "mercado", "_id": update["_id"], "status": 200, "result": "updated",
            }}]}

    capture = Capture()
    restore.apply_batch(capture, "mercado", [update])
    restore.apply_batch(capture, "mercado", [update], bulk_gzip=True)
    raw, zipped = [call[2] for call in capture.calls]
    assert "Content-Encoding" not in raw["headers"]
    assert zipped["headers"]["Content-Encoding"] == "gzip"
    assert gzip.decompress(zipped["data"]) == raw["data"]
    assert all((method, path) == ("POST", "/_bulk") for method, path, _ in capture.calls)

    args, target = setup_run(tmp_path, monkeypatch, count=2, limit=1)
    assert restore.run(args) == 0
    before = json.loads(Path(args.state).read_text())["job_sha256"]
    args.resume, args.limit, args.bulk_gzip = True, None, True
    assert restore.run(args) == 0
    after = json.loads(Path(args.state).read_text())
    assert after["job_sha256"] == before
    assert after["status"] == "complete"
    assert target.counts("mercado")["title_embedding"] == 2
