"""Conditional update counts through HTTP and both ES8 provider paths.

Only external ES APIs are replaced; no real cluster or service is contacted.
"""
import copy
from itertools import cycle
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from kdb.entrypoints.http.retrieval.app import app
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
import kdb.retrieval.application.runtime as runtime_state
from tests.retrieval.test_es8_interface import routed_clients


CONDITIONS = [{"platform": "sample"}, {"del_flag": 0}]
QUERY = {"bool": {"must": [{"term": {"platform": "sample"}}, {"term": {"del_flag": 0}}]}}
FIELDS = {"audit_result": 2}


def prepare_serverless(client, index, count):
    client.indices.mapping = {index: {"mappings": {"properties": {}}}}
    client.open_point_in_time = Mock(return_value={"id": "update-count-pit"})
    client.close_point_in_time = Mock(return_value={"succeeded": True})
    hits = [{"_index": index, "_id": str(i), "_seq_no": 7, "_primary_term": 1,
             "sort": [i], "_source": {"audit_result": 2, "ext_info": {"keep": True}}}
            for i in range(count)]
    page = {"_shards": {"total": 1, "successful": 1, "failed": 0},
            "hits": {"total": {"value": count, "relation": "eq"}, "hits": hits}}
    empty = copy.deepcopy(page)
    empty["hits"]["hits"] = []
    client.search = Mock(side_effect=cycle([page, empty] if count else [empty]))
    client.bulk = Mock(return_value={"errors": False, "items": [
        {"index": {"_index": index, "_id": str(i), "status": 200, "result": "updated"}}
        for i in range(count)
    ]})


@pytest.fixture
def update_api(routed_clients, monkeypatch):
    engine, clients = routed_clients
    engine.get_client_by_index("archive_one")
    interface = SearchDataInterface.__new__(SearchDataInterface)
    interface.engine = engine
    monkeypatch.setattr(runtime_state, "SEARCH_DATA_INTERFACE", interface)
    monkeypatch.setattr("kdb.retrieval.engines.es8_search_interface.time.sleep", Mock())
    for client in clients.values():
        client.count = Mock(side_effect=AssertionError("Update counts must come from write responses"))
    return TestClient(app), engine, clients


@pytest.mark.parametrize("provider,index", [("paas", "archive_one"), ("serverless", "qa_one")])
@pytest.mark.parametrize("count", [0, 1, 3])
def test_http_counts_zero_and_repeated_same_value_updates(update_api, provider, index, count):
    api, _, clients = update_api
    client = clients[provider]
    if provider == "paas":
        client.update_by_query = Mock(return_value={"updated": count, "total": count,
                                                   "version_conflicts": 0, "failures": []})
    else:
        prepare_serverless(client, index, count)

    request = {"index_name": index, "update_fields": FIELDS, "conditions": CONDITIONS}
    for _ in range(2):
        response = api.post("/update_by_condition", json=request)
        assert response.status_code == 200
        assert response.json() == {"success": True, "updated_count": count, "message": "条件更新操作完成"}
        assert type(response.json()["updated_count"]) is int

    if provider == "paas":
        assert client.update_by_query.call_count == 2
        for call in client.update_by_query.call_args_list:
            assert call.kwargs["index"] == [index]
            assert call.kwargs["query"] == QUERY
            assert call.kwargs["conflicts"] == "abort"
            assert call.kwargs["script"] == {"lang": "painless",
                "source": "ctx._source['audit_result'] = params.new_audit_result",
                "params": {"new_audit_result": 2}}
    else:
        assert client.open_point_in_time.call_count == client.close_point_in_time.call_count == 2
        assert client.bulk.call_count == (2 if count else 0)
        for call in client.search.call_args_list:
            assert call.kwargs["query"] == QUERY
        for call in client.bulk.call_args_list:
            operations = call.kwargs["operations"]
            assert len(operations) == 2 * count
            assert all(doc == {"audit_result": 2, "ext_info": {"keep": True}}
                       for doc in operations[1::2])
    for client in clients.values():
        client.count.assert_not_called()


def test_http_sums_updates_across_provider_groups(update_api):
    api, _, clients = update_api
    clients["paas"].update_by_query = Mock(side_effect=[
        {"updated": 2, "total": 2}, {"updated": 4, "total": 4},
    ])
    prepare_serverless(clients["serverless"], "qa_one", 3)
    response = api.post("/update_by_condition", json={
        "index_name": "archive_one,qa_one,archive_two", "update_fields": FIELDS, "conditions": CONDITIONS,
    })
    assert response.json() == {"success": True, "updated_count": 9, "message": "条件更新操作完成"}
    assert [call.kwargs["index"] for call in clients["paas"].update_by_query.call_args_list] == [
        ["archive_one"], ["archive_two"],
    ]
    assert clients["serverless"].open_point_in_time.call_args.kwargs["index"] == "qa_one"


@pytest.mark.parametrize("updated", [0, 2])
def test_native_count_uses_updated_not_total(update_api, updated):
    _, engine, clients = update_api
    clients["paas"].update_by_query = Mock(return_value={"updated": updated, "total": 5, "noops": 5 - updated})
    result = engine.update_value("archive_one", FIELDS, CONDITIONS)
    assert type(result) is int and result == updated
    clients["paas"].count.assert_not_called()


@pytest.mark.parametrize("failure", [
    {"updated": 1, "total": 2, "version_conflicts": 1},
    {"updated": 1, "total": 2, "failures": [{"cause": "write failed"}]},
    {"updated": 1, "total": 2, "timed_out": True},
    {"total": 2},
    {"updated": True, "total": 2},
    {"updated": -1, "total": 2},
    {"completed": False, "task": "pending-task"},
    RuntimeError("synthetic transport failure"),
], ids=["conflict", "failure", "timeout", "missing-count", "boolean-count", "negative-count", "pending-task", "transport"])
def test_native_failures_raise_and_http_reports_failure(update_api, failure):
    api, engine, clients = update_api
    clients["paas"].update_by_query = (Mock(side_effect=failure) if isinstance(failure, Exception)
                                      else Mock(return_value=failure))
    with pytest.raises(RuntimeError):
        engine.update_value("archive_one", FIELDS, CONDITIONS)
    response = api.post("/update_by_condition", json={
        "index_name": "archive_one", "update_fields": FIELDS, "conditions": CONDITIONS,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["success"] is False and result["updated_count"] == 0
    assert "可能已有部分更新成功" in result["message"] and "不会自动回滚" in result["message"]


@pytest.mark.parametrize("failure", ["conflict", "failure", "truncated-bulk", "transport", "incomplete-snapshot", "timeout"])
def test_serverless_partial_failures_are_not_success(update_api, failure):
    api, _, clients = update_api
    client = clients["serverless"]
    prepare_serverless(client, "qa_one", 2)
    if failure in {"conflict", "failure"}:
        client.bulk.return_value["errors"] = True
        client.bulk.return_value["items"][1] = {"index": {
            "status": 409 if failure == "conflict" else 500, "error": {"type": failure},
        }}
    elif failure == "truncated-bulk":
        client.bulk.return_value["items"].pop()
    elif failure == "transport":
        client.bulk.side_effect = RuntimeError("synthetic transport failure")
    else:
        client.search = Mock(return_value={"_shards": {"failed": 0}, "timed_out": failure == "timeout",
            "hits": {"total": {"value": 2, "relation": "eq"}, "hits": []}})

    response = api.post("/update_by_condition", json={
        "index_name": "archive_one,qa_one", "update_fields": FIELDS, "conditions": CONDITIONS,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["success"] is False and result["updated_count"] == 0
    assert "可能已有部分更新成功" in result["message"] and "不会自动回滚" in result["message"]
    assert any(name == "update_by_query" for name, _ in clients["paas"].calls)
    client.close_point_in_time.assert_called_once_with(id="update-count-pit")


def test_empty_patch_is_zero_without_backend_calls(update_api):
    api, engine, clients = update_api
    result = engine.update_value("qa_one", {}, CONDITIONS)
    assert type(result) is int and result == 0
    response = api.post("/update_by_condition", json={
        "index_name": "qa_one", "update_fields": {}, "conditions": CONDITIONS,
    })
    assert response.status_code == 400
    assert all(not client.calls for client in clients.values())
