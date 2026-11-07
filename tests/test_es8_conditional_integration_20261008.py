"""Integrated old-project condition update/API contracts with offline ES boundaries."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_es8_conditional_integration_20261008.py')
import asyncio
import copy
import ast
import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import Mock
import pytest
import requests
from test_es8_autocreate_20261005 import post_query
from es8_conditional_boundary_20261008 import make_engine, BodyClient, data_rows, matches, make_business, service_module


@pytest.fixture(autouse=True)
def offline_network_guard(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', Mock(side_effect=AssertionError('network forbidden')))
    monkeypatch.setattr(requests.Session, 'request', Mock(side_effect=AssertionError('HTTP network forbidden')))
class MutationClient(BodyClient):
    def __init__(self, docs=()):
        super().__init__(docs)
        self.snapshot = []
        self.current_pit = None
        self.status = 200
        self.bulk_response = None
        self.native_response = None
        for n, row in enumerate(self.docs):
            row.setdefault("_seq_no", n + 1)
            row.setdefault("_primary_term", 2)
            row.setdefault("_routing", "route-" + str(n))

    def open_point_in_time(self, **kwargs):
        super().open_point_in_time(**kwargs)
        self.snapshot = copy.deepcopy(self.docs)
        self.current_pit = "pit-1"
        return {"id": self.current_pit}

    def close_point_in_time(self, **kwargs):
        assert kwargs["id"] == self.current_pit
        return super().close_point_in_time(**kwargs)

    def search(self, **kwargs):
        if "pit" not in kwargs:
            return super().search(**kwargs)
        self.calls.append(("search", copy.deepcopy(kwargs)))
        assert kwargs["pit"]["id"] == self.current_pit
        self.current_pit = "pit-" + str(int(self.current_pit.split("-")[-1]) + 1)
        if self.responses:
            response = copy.deepcopy(self.responses.pop(0))
            response["pit_id"] = self.current_pit
            return response
        names = self.pit_indexes.split(",")
        selected = []
        for n, row in enumerate(self.snapshot):
            if row["_index"] in names and matches(row, kwargs["query"]):
                row = copy.deepcopy(row)
                row["sort"] = [n]
                selected.append(row)
        total = len(selected)
        cursor = (kwargs.get("search_after") or [-1])[0]
        selected = [row for row in selected if row["sort"][0] > cursor][:kwargs["size"]]
        return {"pit_id": self.current_pit, "_shards": {"failed": 0},
                "hits": {"total": {"value": total, "relation": "eq"}, "hits": selected}}

    def bulk(self, **kwargs):
        self.calls.append(("bulk", copy.deepcopy(kwargs)))
        if self.bulk_response is not None:
            return copy.deepcopy(self.bulk_response)
        items = []
        operations = kwargs["operations"]
        for n in range(0, len(operations), 2):
            kind, action = next(iter(operations[n].items()))
            assert kind == "index", "object replacement must not merge an old object"
            row = next(row for row in self.docs if (row["_index"], row["_id"], row["_routing"]) ==
                       (action["_index"], action["_id"], action.get("routing")))
            status = 409 if self.simulate_conflict else self.status
            if status == 200:
                assert (action["if_seq_no"], action["if_primary_term"]) == (row["_seq_no"], row["_primary_term"])
                row["_source"] = copy.deepcopy(operations[n + 1])
                row["_seq_no"] += 1
                items.append({kind: {"status": 200, "result": "updated", "_index": row["_index"], "_id": row["_id"]}})
            else:
                items.append({kind: {"status": status, "error": {"type": "synthetic_failure"}}})
        return {"errors": any(item["index"]["status"] >= 300 for item in items), "items": items}

    def update_by_query(self, **kwargs):
        if self.native_response is not None:
            self.calls.append(("update_by_query", copy.deepcopy(kwargs)))
            return copy.deepcopy(self.native_response)
        result = super().update_by_query(**kwargs)
        names = kwargs["index"]
        names = names.split(",") if isinstance(names, str) else names
        count = sum(row["_index"] in names and matches(row, kwargs.get("query", kwargs.get("body", {}).get("query"))) for row in self.docs)
        return dict(result, updated=count, total=count)

    simulate_conflict = False


def source_rows(n=3):
    rows = [row for row in data_rows(n) if row["_index"] == "a"]
    for row in rows:
        row["_source"].update(from_type_norm="document", custom={"keep": [1, None, {"z": True}]},
                               image_indexes=[{"text": "image", "embedding": [0, 0, 1]}])
    return rows


@pytest.mark.parametrize("method", ["update_value", "update_by_query"])
@pytest.mark.parametrize("count", [0, 1, 51, 103])
def test_serverless_condition_updates_keep_original_payload(method, count, monkeypatch):
    monkeypatch.setattr("knowledge_interface_tools.es8_search_interface.time.sleep", lambda *_: None)
    client = MutationClient(source_rows(count))
    before = copy.deepcopy(client.docs)
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    patch = {"del_flag": 1}
    conditions = [{"data_type": "qa"}, {"del_flag": 0}]
    if method == "update_value":
        assert engine.update_value("a", patch, conditions) is True
    else:
        result = engine.update_by_query("a", {"term": {"del_flag": 0}}, patch, -1)
        assert result == {"updated": count, "total": count, "version_conflicts": 0, "failures": []}
    assert patch == {"del_flag": 1} and conditions == [{"data_type": "qa"}, {"del_flag": 0}]
    for old, new in zip(before, client.docs):
        assert new["_source"] == dict(old["_source"], del_flag=1)
        assert (new["_index"], new["_id"], new["_routing"]) == (old["_index"], old["_id"], old["_routing"])
    assert not any(name == "update_by_query" for name, _ in client.calls)
    assert client.closed_pits == [client.current_pit]
    assert all(params["source"] is True and params["size"] <= 50 for name, params in client.calls if name == "search")


def test_same_value_assignment_matches_legacy_script_count():
    client = MutationClient(source_rows(1))
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    assert engine.update_by_query("a", {"match_all": {}}, {"del_flag": 0}, -1)["updated"] == 1
    assert client.docs[0]["_seq_no"] == 2


def test_object_replacement_and_dotted_assignment():
    client = MutationClient(source_rows(1))
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    patch = {"ext_info": {"new": 1}, "ext_info.other": None, "indexes": [{"text": "new", "embedding": [1, 1, 0]}]}
    engine.update_by_query("a", {"match_all": {}}, patch, -1)
    source = client.docs[0]["_source"]
    assert source["ext_info"] == {"new": 1, "other": None}
    assert source["indexes"] == patch["indexes"] and source["custom"]["keep"] == [1, None, {"z": True}]
    assert patch["ext_info"] == {"new": 1}


@pytest.mark.parametrize("path", ["indexes.embedding", "missing.child", "del_flag.child"])
def test_bad_parent_never_overwrites_nested_list(path):
    client = MutationClient(source_rows(1))
    before = copy.deepcopy(client.docs)
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    with pytest.raises((ValueError, RuntimeError)):
        engine.update_by_query("a", {"match_all": {}}, {path: 1}, -1)
    assert client.docs == before and not any(name == "bulk" for name, _ in client.calls)
    assert client.closed_pits == [client.current_pit]


@pytest.mark.parametrize("status,method", [(409, "update_value"), (409, "update_by_query"), (400, "update_value"), (400, "update_by_query")])
def test_partial_failure_and_conflict_policy(status, method):
    client = MutationClient(source_rows(1)); client.status = status
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    if method == "update_value":
        assert engine.update_value("a", {"del_flag": 1}, [{"del_flag": 0}]) is False
    elif status == 409:
        assert engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1) == {
            "updated": 0, "total": 1, "version_conflicts": 1, "failures": []}
    else:
        with pytest.raises(RuntimeError):
            engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1)
    assert client.closed_pits == [client.current_pit]
    assert client.docs[0]["_source"]["del_flag"] == 0


@pytest.mark.parametrize("fault", ["missing_source", "missing_version", "missing_cursor", "early_empty", "partial_shards"])
def test_incomplete_snapshot_is_never_success(fault, monkeypatch):
    monkeypatch.setattr("knowledge_interface_tools.es8_search_interface.time.sleep", lambda *_: None)
    client = MutationClient(source_rows(1))
    row = copy.deepcopy(client.docs[0]); row["sort"] = [0]
    wire = {"hits": {"total": {"value": 1, "relation": "eq"}, "hits": [row]}, "_shards": {"failed": 0}}
    if fault.startswith("missing"):
        row.pop({"missing_source": "_source", "missing_version": "_seq_no", "missing_cursor": "sort"}[fault])
    elif fault == "early_empty":
        wire["hits"]["hits"] = []
    else:
        wire["_shards"]["failed"] = 1
    client.responses = [wire] * 4
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    with pytest.raises(RuntimeError):
        engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1)
    assert not any(name == "bulk" for name, _ in client.calls)
    assert client.closed_pits == [client.current_pit]


@pytest.mark.parametrize("wire", [{"items": []}, {"error": {"type": "terminal"}},
    {"items": [{"index": {"status": 200, "result": "created"}}]},
    {"errors": True, "items": [{"index": {"status": 200, "result": "updated"}}]}])
def test_bulk_result_integrity(wire):
    client = MutationClient(source_rows(1)); client.bulk_response = wire
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    with pytest.raises(RuntimeError):
        engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1)
    assert client.closed_pits == [client.current_pit]


@pytest.mark.parametrize("status", [200, 400])
def test_original_business_condition_service(monkeypatch, tmp_path, status):
    client = MutationClient(source_rows(1)); client.status = status
    iface = make_business(monkeypatch, tmp_path, {"serverless": client, "paas": MutationClient()})
    svc = service_module(monkeypatch, iface)
    request = svc.UpdateByConditionRequest(index_name="a", update_fields={"del_flag": 1}, conditions=[{"_id": "0"}])
    payload = asyncio.run(svc.update_by_condition(request)).model_dump()
    assert payload["success"] is (status == 200)
    assert client.docs[0]["_source"]["del_flag"] == int(status == 200)


@pytest.mark.parametrize("status", [200, 400])
def test_original_file_soft_delete_success_and_failure(monkeypatch, tmp_path, status):
    client = MutationClient(source_rows(1)); client.status = status
    iface = make_business(monkeypatch, tmp_path, {"serverless": client, "paas": MutationClient()})
    # Boundary count/aggregation fixture does not implement terms aggregation.
    client.count = Mock(return_value={"count": 1, "_shards": {"failed": 0}})
    if status == 400:
        with pytest.raises(RuntimeError):
            iface.delete_by_file("a", ["f.pdf"], snapshot_dir=str(tmp_path / "snapshot"))
    else:
        result = iface.delete_by_file("a", ["f.pdf"], snapshot_dir=str(tmp_path / "snapshot"))
        assert result["success"] and result["deleted_count"] == 1
        assert __import__("pathlib").Path(result["snapshot_path"]).exists()
    assert client.docs[0]["_source"]["del_flag"] == int(status == 200)


@pytest.mark.parametrize("indexes", ["a,c", "a,b,c"])
def test_routing_and_provider_dispatch(indexes):
    clients = {"serverless": MutationClient(data_rows(1)), "paas": MutationClient(data_rows(1))}
    engine = make_engine(clients)
    result = engine.update_by_query(indexes, {"match_all": {}}, {"del_flag": 1}, -1)
    assert result == {"updated": len(indexes.split(",")), "total": len(indexes.split(",")), "version_conflicts": 0, "failures": []}
    assert not any(name == "update_by_query" for name, _ in clients["serverless"].calls)
    native = [params for name, params in clients["paas"].calls if name == "update_by_query"]
    assert bool(native) == ("b" in indexes)
    assert all(params["index"] == ["b"] and params["requests_per_second"] == -1 for params in native)


@pytest.mark.parametrize("oversized", [False, True])
def test_bulk_payload_size_boundary(oversized):
    rows = source_rows(1 if oversized else 3)
    for row in rows:
        row["_source"]["payload"] = "a" * (9 * 1024 * 1024 if oversized else 3 * 1024 * 1024)
    client = MutationClient(rows)
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    if oversized:
        with pytest.raises(RuntimeError):
            engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1)
        assert not any(name == "bulk" for name, _ in client.calls)
    else:
        assert engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1}, -1)["updated"] == 3
        assert [len(params["operations"]) // 2 for name, params in client.calls if name == "bulk"] == [2, 1]


@pytest.mark.parametrize("wire", [{"completed": False, "task": "x"}, {"completed": True},
    {"timed_out": True, "updated": 0, "total": 0}, {},
    {"updated": 0, "total": 1, "failures": [{"cause": {"type": "mapper_parsing_exception"}}]},
    {"completed": True, "response": {"updated": 2, "total": 2, "failures": []}}])
def test_checked_task_envelopes(wire):
    client = MutationClient(); client.native_response = wire
    engine = make_engine({"serverless": MutationClient(), "paas": client}, routes={"a": "paas"})
    if wire.get("response"):
        assert engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1})["updated"] == 2
    else:
        with pytest.raises(RuntimeError):
            engine.update_by_query("a", {"match_all": {}}, {"del_flag": 1})


def test_conditions_are_AND_and_untargeted_rows_unchanged():
    rows = source_rows(3)
    rows[1]["_source"]["del_flag"] = 1
    rows[2]["_source"]["data_type"] = "segment"
    client = MutationClient(rows)
    before = copy.deepcopy(client.docs)
    engine = make_engine({"serverless": client, "paas": MutationClient()})
    assert engine.update_value("a", {"del_flag": 1}, [{"del_flag": 0}, {"data_type": "qa"}])
    assert client.docs[0]["_source"] == dict(before[0]["_source"], del_flag=1)
    assert client.docs[1:] == before[1:]


@pytest.mark.parametrize('status', [200, 400])
@pytest.mark.parametrize('endpoint', ['/update_by_condition', '/delete_by_file'])
def test_http_original_condition_and_file_delete(monkeypatch, tmp_path, status, endpoint):
    client = MutationClient(source_rows(1)); client.status = status
    before = copy.deepcopy(client.docs[0]['_source'])
    iface = make_business(monkeypatch, tmp_path, {'serverless': client, 'paas': MutationClient()})
    service = service_module(monkeypatch, iface)
    if endpoint == '/update_by_condition':
        request = {'index_name': 'a', 'update_fields': {'del_flag': 1}, 'conditions': [{'_id': '0'}]}
    else:
        client.count = Mock(return_value={'count': 1, '_shards': {'failed': 0}})
        request = {'index_name': 'a', 'file_names': ['f.pdf'], 'snapshot_dir': str(tmp_path / 'snapshots')}
    original = copy.deepcopy(request)
    response = asyncio.run(post_query(service, endpoint, request))
    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is (status == 200)
    assert client.docs[0]['_source'] == dict(before, del_flag=int(status == 200))
    assert request == original
    assert not any(method == 'update_by_query' for method, _ in client.calls)
    assert client.closed_pits == [client.current_pit]
    if endpoint == '/delete_by_file' and status == 200:
        assert payload['deleted_count'] == 1


@pytest.mark.parametrize('storage', [{'enabled': False}, {'excludes': ['indexes.embedding']}, {'includes': ['title']}])
@pytest.mark.parametrize('method', ['update_value', 'update_by_query'])
def test_stored_source_filter_stops_before_write(storage, method):
    client = MutationClient(source_rows(1))
    client.indices.get_mapping.return_value = {'a': {'mappings': {'_source': storage}}}
    before = copy.deepcopy(client.docs)
    engine = make_engine({'serverless': client, 'paas': MutationClient()})
    if method == 'update_value':
        assert engine.update_value('a', {'del_flag': 1}, [{'_id': '0'}]) is False
    else:
        with pytest.raises(RuntimeError, match='完整存储source'):
            engine.update_by_query('a', {'match_all': {}}, {'del_flag': 1})
    assert client.docs == before
    assert not any(name in {'bulk', 'open_point_in_time'} for name, _ in client.calls)


@pytest.mark.parametrize('fault', ['partial_shards', 'timeout'])
def test_retry_rotates_pit_and_preserves_source(monkeypatch, fault):
    monkeypatch.setattr('knowledge_interface_tools.es8_search_interface.time.sleep', lambda *_: None)
    client = MutationClient(source_rows(1))
    before = copy.deepcopy(client.docs[0]['_source'])
    row = copy.deepcopy(client.docs[0]); row['sort'] = [0]
    success = {'_shards': {'failed': 0}, 'hits': {'total': {'value': 1, 'relation': 'eq'}, 'hits': [row]}}
    failed = copy.deepcopy(success)
    if fault == 'partial_shards':
        failed['_shards']['failed'] = 1
    else:
        failed['timed_out'] = True
    client.responses = [failed, success]
    engine = make_engine({'serverless': client, 'paas': MutationClient()})
    assert engine.update_by_query('a', {'match_all': {}}, {'del_flag': 1}, -1)['updated'] == 1
    calls = [kw for name, kw in client.calls if name == 'search']
    assert [kw['pit']['id'] for kw in calls] == ['pit-1', 'pit-2', 'pit-3']
    assert client.closed_pits == ['pit-4']
    assert client.docs[0]['_source'] == dict(before, del_flag=1)
    assert len([kw for name, kw in client.calls if name == 'bulk']) == 1


@pytest.mark.parametrize('method', ['update_value', 'update_by_query'])
def test_native_task_error_is_not_success(method):
    client = MutationClient()
    client.native_response = {'completed': True, 'task': {}, 'error': {'type': 'serverless_check_exception', 'reason': 'script_unsupported'}}
    engine = make_engine({'serverless': MutationClient(), 'paas': client}, routes={'a': 'paas'})
    if method == 'update_value':
        assert engine.update_value('a', {'del_flag': 1}, [{'_id': '0'}]) is False
    else:
        with pytest.raises(RuntimeError, match='conditional update failed'):
            engine.update_by_query('a', {'match_all': {}}, {'del_flag': 1})
    assert [name for name, _ in client.calls] == ['update_by_query']


def test_public_update_signatures_and_existing_business_are_unchanged():
    root = Path(__legacy_source_file__).resolve().parents[1]
    review = root / 'docs/reviews/es817_conditional_update_integration_20261008'
    baseline = json.loads((review / 'baseline.json').read_text())
    for name, expected in baseline['source_hashes'].items():
        # Both engine adapters now add opt-in maintenance capabilities. The
        # existing business/service consumers remain pinned by these hashes.
        if name.endswith(('/es8_search_interface.py', '/es_search_interface.py')):
            continue
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    old = ast.parse((review / 'before_es8_search_interface.py').read_text())
    new = ast.parse((root / 'knowledge_interface_tools/es8_search_interface.py').read_text())
    old_class = next(node for node in old.body if isinstance(node, ast.ClassDef))
    new_class = next(node for node in new.body if isinstance(node, ast.ClassDef))
    for name in ['update_value', 'update_by_query', 'insert', 'update', 'delete', 'search', 'search_multi', 'count_by_query']:
        old_method = next(node for node in old_class.body if isinstance(node, ast.FunctionDef) and node.name == name)
        new_method = next(node for node in new_class.body if isinstance(node, ast.FunctionDef) and node.name == name)
        assert ast.dump(old_method.args) == ast.dump(new_method.args)
