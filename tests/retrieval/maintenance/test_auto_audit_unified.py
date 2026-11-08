import kdb.entrypoints.scheduled.auto_audit as _entrypoints_scheduled_auto_audit
import kdb.retrieval.engines.providers.es7 as _engines_providers_es7
import kdb.retrieval.engines.providers.opensearch2 as _engines_providers_opensearch2
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
"""Real audit -> factory -> engine behavior with only ES I/O replaced."""
import copy
import json
import socket
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import kdb.retrieval.maintenance.auto_audit as audit
import kdb.retrieval.engines.factory as legacy
from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.retrieval.engines.es_maintenance import run_native_update
from kdb.retrieval.engines.es_maintenance import wait_for_update_task

NOW = datetime(2026, 10, 19, 12)
SHARDS = {"total": 1, "successful": 1, "failed": 0}


def matches(source, query):
    """Independent exact matcher; unsupported fixture DSL must fail loudly."""
    if "match_all" in query:
        return True
    if "bool" in query:
        body = query["bool"]
        return (all(matches(source, clause) for clause in body.get("must", []) + body.get("filter", []))
                and not any(matches(source, clause) for clause in body.get("must_not", [])))
    for key in ("term", "terms"):
        if key in query:
            field, expected = next(iter(query[key].items()))
            return source.get(field) in (expected if key == "terms" else [expected])
    if "range" in query:
        field, limits = next(iter(query["range"].items()))
        assert set(limits) == {"lte"}
        return source.get(field) is not None and source[field] <= limits["lte"]
    raise AssertionError("Unsupported fixture query: " + str(query))


def rows(index="payoneer_olive"):
    """Include boundary/soft-delete/held-segment/manual-review counterexamples."""
    patches = [
        {}, {"quality_level": "mid"}, {"data_type": "segment"},
        {"data_type": "segment", "quality_level": "mid"},
        {"from_type_norm": "auto_learning"}, {"audit_result": 1},
        {"del_flag": 1}, {"insert_time": "2026-10-18 12:00:01"},
        {"insert_time": "2026-10-18 12:00:00", "from_type_norm": "html"},
        {"quality_level": None},
    ]
    output = []
    for n, patch in enumerate(patches):
        source = {
            "title": "title", "content": "unaltered text", "data_type": "qa",
            "audit_result": -1, "quality_level": "high", "del_flag": 0,
            "insert_time": "2026-10-16 12:00:00", "update_time": "2026-10-16 12:00:00",
            "from_type_norm": "document", "ext_info": {"keep": [1, None, {"x": True}]},
            "title_embedding": [1, 0, 0], "content_embedding": [0, 1, 0],
            "indexes": [{"text": "question", "embedding": [0, 0, 1]}],
            "image_indexes": [{"text": "image", "embedding": [1, 1, 0]}],
        }
        source.update(patch)
        output.append({"_index": index, "_id": str(n), "_source": source,
                       "_seq_no": n + 1, "_primary_term": 2, "_routing": "route-" + str(n)})
    return output


class AuditClient:
    """ES wire boundary, including a snapshot and real CAS rejection semantics."""

    def __init__(self, data=(), inventory=(), version="8.17.0"):
        self.docs = copy.deepcopy(list(data))
        self.inventory = list(inventory)
        self.calls = []
        self.version = version
        self.closed = False
        self.current_pit = 0
        self.closed_pits = []
        self.native_error = None
        self.fail_after_native_calls = 0
        self.partial_count = False
        self.aggregate_fault = None
        self.concurrent_manual = False
        self.indices = SimpleNamespace(
            exists=Mock(side_effect=lambda **kw: kw["index"] in self.inventory),
            create=Mock(side_effect=AssertionError("must not create")),
            put_mapping=Mock(side_effect=AssertionError("must not update mapping")),
            get_mapping=Mock(side_effect=lambda **kw: {name: {"mappings": {}} for name in kw["index"]}),
        )
        self.cat = SimpleNamespace(indices=Mock(side_effect=lambda **kw: [{"index": name} for name in self.inventory]))

    def info(self):
        return {"version": {"number": self.version}}

    def options(self, **kwargs):
        self.calls.append(("options", kwargs))
        return self

    def count(self, **kwargs):
        self.calls.append(("count", copy.deepcopy(kwargs)))
        query = kwargs.get("query", kwargs.get("body", {}).get("query"))
        shards = {"total": 1, "successful": 0, "failed": 1} if self.partial_count else SHARDS
        return {"count": sum(row["_index"] == kwargs["index"] and matches(row["_source"], query) for row in self.docs), "_shards": shards}

    def search(self, **kwargs):
        self.calls.append(("search", copy.deepcopy(kwargs)))
        body = kwargs.get("body", kwargs)
        if "pit" in body:
            assert body["pit"]["id"] == "pit-" + str(self.current_pit)
            self.current_pit += 1
            selected = [dict(copy.deepcopy(row), sort=[n]) for n, row in enumerate(self.snapshot) if matches(row["_source"], body["query"])]
            after = (body.get("search_after") or [-1])[0]
            return {"pit_id": "pit-" + str(self.current_pit), "_shards": SHARDS,
                    "hits": {"total": {"value": len(selected), "relation": "eq"},
                             "hits": [row for row in selected if row["sort"][0] > after][:body["size"]]}}
        aggregation = body.get("aggs", body.get("aggregations"))
        assert aggregation and body["size"] == 0
        field = aggregation["values"]["terms"]["field"]
        counts = Counter(row["_source"].get(field) for row in self.docs if row["_index"] == kwargs["index"] and matches(row["_source"], body["query"]))
        values = {"buckets": [{"key": key, "doc_count": value} for key, value in counts.items() if key is not None],
                  "sum_other_doc_count": 0, "doc_count_error_upper_bound": 0}
        if self.aggregate_fault:
            values[self.aggregate_fault] = 1
        return {"_shards": SHARDS, "aggregations": {"values": values}}

    def open_point_in_time(self, **kwargs):
        self.calls.append(("open_point_in_time", kwargs))
        self.snapshot = copy.deepcopy([row for row in self.docs if row["_index"] in kwargs["index"].split(",")])
        self.current_pit += 1
        return {"id": "pit-" + str(self.current_pit)}

    def close_point_in_time(self, **kwargs):
        assert kwargs["id"] == "pit-" + str(self.current_pit)
        self.closed_pits.append(kwargs["id"])

    def bulk(self, **kwargs):
        self.calls.append(("bulk", copy.deepcopy(kwargs)))
        if self.concurrent_manual:
            row = self.docs[0]
            row["_source"]["audit_result"] = 1
            row["_seq_no"] += 1
            self.concurrent_manual = False
        items = []
        for n in range(0, len(kwargs["operations"]), 2):
            action = kwargs["operations"][n]["index"]
            row = next(row for row in self.docs if (row["_id"], row["_index"], row["_routing"]) == (action["_id"], action["_index"], action["routing"]))
            if (row["_seq_no"], row["_primary_term"]) != (action["if_seq_no"], action["if_primary_term"]):
                items.append({"index": {"status": 409, "error": {"type": "version_conflict"}}})
            else:
                row["_source"] = copy.deepcopy(kwargs["operations"][n + 1])
                row["_seq_no"] += 1
                items.append({"index": {"status": 200, "result": "updated", "_index": row["_index"], "_id": row["_id"]}})
        return {"items": items, "errors": any(item["index"]["status"] != 200 for item in items)}

    def update_by_query(self, **kwargs):
        self.calls.append(("update_by_query", copy.deepcopy(kwargs)))
        if self.native_error and sum(name == "update_by_query" for name, _ in self.calls) > self.fail_after_native_calls:
            return copy.deepcopy(self.native_error)
        body = kwargs.get("body", kwargs)
        value = next(iter(body["script"]["params"].values()))
        names = kwargs["index"] if isinstance(kwargs["index"], list) else [kwargs["index"]]
        selected = [row for row in self.docs if row["_index"] in names and matches(row["_source"], body["query"])]
        for row in selected:
            row["_source"]["audit_result"] = value
        return {"updated": len(selected), "total": len(selected), "version_conflicts": 0, "failures": []}

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("offline test")))
    monkeypatch.setattr("kdb.retrieval.engines.es8_search_interface.time.sleep", lambda *_: None)


@pytest.fixture
def setup_audit(tmp_path, monkeypatch):
    def build(provider="paas", data=None):
        index = "payoneer_olive" if provider == "paas" else "mercado_local"
        clients = {"serverless": AuditClient(inventory=[".system", "mercado_local", "payoneer_olive"]),
                   "paas": AuditClient(inventory=["payoneer_olive", "mercado_local"])}
        clients[provider].docs = copy.deepcopy(rows(index) if data is None else data)
        monkeypatch.setattr(IndexClientRouter, "_create_client", lambda self, cfg: clients[cfg["hosts"][0]])
        path = tmp_path / "engine.json"
        path.write_text(json.dumps({"es_version": "8.17", "index_name": "unused_default",
            "vector_fields": {"indexes_embedding": 3}, "default_provider": "serverless",
            "providers": {name: {"hosts": [name]} for name in clients},
            "index_routes": {"payoneer*": "paas"},
            "extra_params": {"recall_mode": "dual", "ensure_index_on_init": True, "auto_update_mapping": True}}))
        obj = audit.AutoAuditProcessor(str(path), now=NOW)
        return obj, clients, index, path
    return build


@pytest.mark.parametrize("provider", ["paas", "serverless"])
def test_real_factory_audit_preserves_policy_and_entire_document(setup_audit, provider):
    obj, clients, index, _ = setup_audit(provider)
    before = copy.deepcopy(clients[provider].docs)
    result = obj.auto_audit_for_indexes([index], ["document", "html"])
    entry = result["details"][index]
    assert entry["status"] == "success"
    stats = entry["result"]["stats_before"]
    assert (stats["total_count"], stats["high_count"], stats["other_count"], stats["unchanged_count"], stats["soft_deleted_count"]) == (7, 4, 2, 1, 1)
    assert entry["result"]["total_updated"] == 6 and entry["result"]["remaining_eligible"] == 0
    for n, (old, new) in enumerate(zip(before, clients[provider].docs)):
        expected = copy.deepcopy(old["_source"])
        if n in [0, 2, 6, 8]: expected["audit_result"] = 2
        if n in [1, 9]: expected["audit_result"] = 0
        assert new["_source"] == expected
        assert (new["_id"], new["_routing"], new["_index"]) == (old["_id"], old["_routing"], old["_index"])
    assert not any(name == "update_by_query" for name, _ in clients[provider].calls) if provider == "serverless" else True
    assert len(clients["serverless" if provider == "paas" else "paas"].calls) == 0
    for client in clients.values():
        client.indices.create.assert_not_called();client.indices.put_mapping.assert_not_called()
    assert obj.engine._impl._ensure_index_on_init is False
    obj.close()
    assert clients[provider].closed


@pytest.mark.parametrize("provider", ["paas", "serverless"])
def test_dry_run_and_missing_index_do_not_write_or_create(setup_audit, provider):
    obj, clients, index, _ = setup_audit(provider)
    result = obj.auto_audit_for_indexes([index, "missing"], ["document", "html"], dry_run=True)
    assert result["details"][index]["status"] == "dry_run"
    assert result["details"]["missing"]["status"] == "failed"
    assert result["summary"]["total_docs_updated"] == 0
    assert not any(name in {"bulk", "update_by_query", "open_point_in_time"} for client in clients.values() for name, _ in client.calls)
    for client in clients.values(): client.indices.create.assert_not_called()


def test_inventory_uses_all_authoritative_routes_and_propagates_failure(setup_audit):
    obj, clients, _, _ = setup_audit()
    assert obj.get_all_indexes() == ["mercado_local", "payoneer_olive"]
    clients["paas"].cat.indices.side_effect = RuntimeError("offline provider")
    with pytest.raises(RuntimeError): obj.get_all_indexes()


@pytest.mark.parametrize("fault", ["sum_other_doc_count", "doc_count_error_upper_bound", "partial_count"])
def test_incomplete_counts_are_failures_not_zero(setup_audit, fault):
    obj, clients, index, _ = setup_audit()
    if fault == "partial_count": clients["paas"].partial_count = True
    else: clients["paas"].aggregate_fault = fault
    result = obj.auto_audit_for_indexes([index], ["document", "html"], dry_run=True)
    assert result["summary"]["failed_count"] == 1
    assert not any(name == "update_by_query" for name, _ in clients["paas"].calls)


def test_serverless_concurrent_manual_review_survives_and_is_reported(setup_audit):
    obj, clients, index, _ = setup_audit("serverless")
    clients["serverless"].concurrent_manual = True
    result = obj.auto_audit_for_indexes([index], ["document", "html"])
    assert clients["serverless"].docs[0]["_source"]["audit_result"] == 1
    entry = result["details"][index]
    assert entry["status"] == "partial" and entry["result"]["version_conflicts"] == 1
    assert result["summary"]["failed_count"] == 1
    repeated = obj.auto_audit_for_indexes([index], ["document", "html"])
    assert repeated["summary"]["total_docs_updated"] == 0
    assert clients["serverless"].docs[0]["_source"]["audit_result"] == 1


def test_paas_failure_and_cli_nonzero(setup_audit, monkeypatch, tmp_path):
    obj, clients, index, path = setup_audit()
    clients["paas"].native_error = {"updated": 1, "total": 2, "failures": [{"cause": "failure"}]}
    monkeypatch.setattr(audit, "AutoAuditProcessor", lambda *a, **kw: obj)
    report = tmp_path / "report.json"
    assert _entrypoints_scheduled_auto_audit.main(["--config", str(path), "--index", index, "--from-type-norm", "document,html", "--report-json", str(report)]) == 1
    result = json.loads(report.read_text())
    entry = result["details"][index]["result"]
    assert entry["accounting_complete"] is False and entry["complete"] is False
    assert entry["error"]["stage"] == "high"
    assert clients["paas"].closed


def test_serverless_multiple_batches_and_latest_pit_closed(setup_audit):
    data = [dict(copy.deepcopy(rows("mercado_local")[0]), _id=str(n), _seq_no=n + 1, _routing=str(n)) for n in range(61)]
    obj, clients, index, _ = setup_audit("serverless", data)
    result = obj.auto_audit_for_indexes([index], ["document", "html"], scroll_size=15)
    assert result["summary"]["total_docs_updated"] == 61
    calls = clients["serverless"].calls
    assert all(call["size"] == 15 for name, call in calls if name == "search" and "pit" in call)
    assert len([1 for name, _ in calls if name == "bulk"]) == 5
    assert clients["serverless"].closed_pits == ["pit-" + str(clients["serverless"].current_pit)]


def test_config_pointer_and_old_cli_config_shape(setup_audit, tmp_path):
    obj, clients, index, path = setup_audit()
    service = tmp_path / "search.json"
    service.write_text(json.dumps({"search_engine_config_path": str(path)}))
    assert audit.load_engine_config_path(None, str(service)) == path
    assert audit.load_engine_config_path(str(path), None) == path
    for first, second in [(None, None), (str(path), str(service))]:
        with pytest.raises(ValueError): audit.load_engine_config_path(first, second)
    service.write_text("{}")
    with pytest.raises(ValueError): audit.load_engine_config_path(None, str(service))


@pytest.mark.parametrize("version", ["es7", "opensearch2"])
def test_legacy_real_factory_maintenance_and_original_mode(monkeypatch, tmp_path, version):
    client = AuditClient(rows("old"), ["old"], "7.10.0" if version == "es7" else "2.19.0")
    monkeypatch.setattr(_engines_providers_es7 if version == "es7" else _engines_providers_opensearch2, "Elasticsearch", Mock(return_value=client))
    cls = _engines_providers_es7.EsSearchInterfaceOri if version == "es7" else _engines_providers_opensearch2.EsSearchInterfaceOpen
    ensure = Mock()
    monkeypatch.setattr(cls, "_ensure_index", ensure)
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"hosts": ["legacy"], "index_name": "default", "es_version": version}))
    obj = audit.AutoAuditProcessor(str(path), now=NOW)
    ensure.assert_not_called()
    assert obj.get_all_indexes() == ["old"]
    result = obj.auto_audit_for_indexes(["old"], ["document", "html"])
    assert result["summary"]["total_docs_updated"] == 6
    native = [call for name, call in client.calls if name == "update_by_query"]
    assert all(call["scroll_size"] == 30 and "max_docs" not in call for call in native)
    legacy.EsSearchInterface(config_path=str(path))
    ensure.assert_called_once_with("default")


@pytest.mark.parametrize("bad_name", ["*", "a,b", "_all", "", " a"])
def test_explicit_index_guard(setup_audit, bad_name):
    obj, clients, _, _ = setup_audit()
    result = obj.auto_audit_for_indexes([bad_name], ["document"])
    assert result["summary"]["failed_count"] == 1
    assert not any(client.calls for client in clients.values())


def test_completed_branch_is_retained_when_next_branch_fails(setup_audit):
    obj, clients, index, _ = setup_audit()
    client = clients["paas"]
    client.native_error = {"error": {"type": "rejected"}}
    client.fail_after_native_calls = 1
    result = obj.auto_audit_for_indexes([index], ["document", "html"])
    entry = result["details"][index]["result"]
    assert entry["high_quality"]["updated"] == result["summary"]["total_docs_updated"] == 4
    assert entry["error"]["stage"] == "other" and entry["accounting_complete"] is False
    assert entry["remaining_eligible"] is None
    assert client.docs[0]["_source"]["audit_result"] == 2
    assert client.docs[1]["_source"]["audit_result"] == -1


@pytest.mark.parametrize("response", [
    {"updated": 0}, {"updated": True, "total": 0}, {"updated": 0, "total": -1},
    {"updated": 2, "total": 1},
    {"response": {"updated": 1, "total": 1}},
    {"updated": 0, "total": 0, "timed_out": True},
    {"error": {"reason": "write_size blocked"}},
    {"task": {"status": {"updated": 1}}, "error": {"reason": "write_size blocked"}},
])
def test_native_invalid_or_partial_response_cannot_be_success_or_replayed(response):
    client = Mock()
    client.options.return_value = client
    client.update_by_query.return_value = response
    with pytest.raises(RuntimeError): run_native_update(client, {"index": "x"})
    client.update_by_query.assert_called_once()


def test_uncertain_transport_failure_is_not_replayed():
    client = Mock()
    client.options.return_value = client
    client.update_by_query.side_effect = RuntimeError("write_size blocked but outcome unknown")
    with pytest.raises(RuntimeError): run_native_update(client, {"index": "x"})
    client.update_by_query.assert_called_once()


def test_task_timeout_is_not_completion(monkeypatch):
    client = Mock()
    client.tasks.get.return_value = {"completed": False}
    monkeypatch.setattr("kdb.retrieval.engines.es_maintenance.time.monotonic", Mock(side_effect=[0, 1]))
    with pytest.raises(TimeoutError): wait_for_update_task(client, "task-1", timeout_seconds=1)


@pytest.mark.requires_process
def test_shell_wrapper_preserves_status_logs_and_lock(tmp_path):
    import fcntl
    import os
    import shutil
    root = tmp_path / "isolated project"
    (root / "scripts/scheduled").mkdir(parents=True)
    script = root / "scripts/scheduled/auto_audit_all_indexes.sh"
    shutil.copyfile(_PROJECT_ROOT / "scripts/scheduled/auto_audit_all_indexes.sh", script)
    python = root / "fake python"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\necho stderr-marker >&2\nexit 3\n')
    python.chmod(0o700)
    env = dict(os.environ, AUTO_AUDIT_PYTHON=str(python), AUTO_AUDIT_INDEX="payoneer_olive")
    child = subprocess.run(["sh", str(script), "/ignored/legacy/env.sh"], env=env, capture_output=True, timeout=10)
    assert child.returncode == 3
    logs = list((root / "log").glob("auto_audit_all.log.*"))
    assert len(logs) == 1
    text = logs[0].read_text()
    assert "stderr-marker" in text and "--search-config" in text and "payoneer_olive" in text
    assert not (root / "1").exists()
    with (root / "log/auto_audit.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child = subprocess.run(["sh", str(script)], env=env, capture_output=True, timeout=10)
        assert child.returncode == 75
