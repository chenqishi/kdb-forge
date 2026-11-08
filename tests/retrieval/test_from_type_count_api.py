import kdb.retrieval.application.runtime as retrieval_runtime
import kdb.retrieval.engines.providers.es7 as _engines_providers_es7
import kdb.retrieval.engines.providers.opensearch2 as _engines_providers_opensearch2
"""Actual HTTP/business/factory/engine count contracts; only external clients replaced."""
import asyncio
import copy
from functools import partial
from unittest.mock import Mock

import pytest

import kdb.retrieval.engines.factory as factories
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from tests.retrieval.test_es8_autocreate import fixture_service
from tests.retrieval.test_es8_autocreate import post_query

START, END = "2026-09-01 00:00:00", "2026-09-30 23:59:59"
COMPLETE = {"count": 0, "_shards": {"total": 2, "successful": 2, "failed": 0}}


def count_documents(client, **kwargs):
    client.calls.append(("count", copy.deepcopy(kwargs)))
    query = kwargs.get("query", kwargs.get("body", {}).get("query"))
    docs = client.docs[kwargs["index"]]
    for item in query["bool"]["filter"]:
        if "term" in item:
            field, value = next(iter(item["term"].items()))
            docs = [doc for doc in docs if doc.get(field) == value]
        else:
            field, limits = next(iter(item["range"].items()))
            docs = [doc for doc in docs if field in doc and limits["gte"] <= doc[field] <= limits["lte"]]
    return dict(copy.deepcopy(COMPLETE), count=len(docs))


@pytest.fixture
def count_service(fixture_service):
    service, engine, clients = fixture_service
    for suffix, provider in (("s", "serverless"), ("p", "paas")):
        docs = [
            {"quality_level": "high", "from_type": "chat_auto", "insert_time": START,
             "del_flag": 0, "audit_result": 2, "data_type": "qa"},
            {"quality_level": "high", "from_type": "chat_auto", "insert_time": END,
             "del_flag": 1, "audit_result": -1, "data_type": "segment"},
            {"quality_level": "high", "from_type": "document", "insert_time": START},
            {"quality_level": "low", "from_type": "chat_auto", "insert_time": START},
            {"quality_level": "high", "from_type": "chat_auto", "insert_time": "2026-08-31 23:59:59"},
            {"quality_level": "high", "from_type": "chat_auto"},
            {"quality_level": "high", "from_type": "chat_auto", "insert_time": "2026-10-01 00:00:00"},
        ]
        client = clients[provider]
        client.docs["public_" + suffix] = docs
        client.count = Mock(side_effect=partial(count_documents, client))
        client.calls.clear()
    return service, engine, clients


def assert_no_index_writes(clients):
    for client in clients.values():
        assert client.create_requests == []
        assert not client.indices.put_mapping.called
        assert all(name == "count" for name, _ in client.calls)


@pytest.mark.parametrize("suffix,provider", [("s", "serverless"), ("p", "paas")])
@pytest.mark.parametrize("params,expected,extra_filters", [
    ({}, 5, []),
    ({"from_type": "chat_auto"}, 5, []),
    ({"from_type": "document"}, 1, []),
    ({"from_type": "not_present"}, 0, []),
    ({"from_type": "chat"}, 0, []),
    ({"start": START}, 5, []),
    ({"end": END}, 5, []),
    ({"start": None, "end": END}, 5, []),
    ({"start": START, "end": END}, 2, [{"range": {"insert_time": {"gte": START, "lte": END}}}]),
    ({"start": END, "end": START}, 0, [{"range": {"insert_time": {"gte": END, "lte": START}}}]),
    ({"start": "0001-01-01 00:00:00", "end": END}, 3,
     [{"range": {"insert_time": {"gte": "0001-01-01 00:00:00", "lte": END}}}]),
])
def test_http_count_filters_and_dates(count_service, suffix, provider, params, expected, extra_filters):
    service, engine, clients = count_service
    checked_before = copy.deepcopy(engine.has_build_index)
    request = dict(params, index_name="public_" + suffix)
    original = copy.deepcopy(request)
    response = asyncio.run(post_query(service, "/get_from_type_count", request))
    assert response.status_code == 200
    assert response.json() == {"success": True, "count": expected, "message": ""}
    assert request == original
    assert clients[provider].count.call_args.kwargs == {
        "index": "public_" + suffix, "query": {"bool": {"filter": [
            {"term": {"quality_level": "high"}},
            {"term": {"from_type": params.get("from_type", "chat_auto")}},
        ] + extra_filters}},
    }
    assert clients["paas" if provider == "serverless" else "serverless"].count.call_count == 0
    assert engine.has_build_index == checked_before
    assert not retrieval_runtime.SEARCH_DATA_INTERFACE.embedding_tools.text2embedding.called
    assert_no_index_writes(clients)


@pytest.mark.parametrize("payload,expected_status,expected_count", [
    ({}, 200, 0), ({"index_name": ""}, 200, 0), ({"index_name": None}, 200, 0),
    ({"indexName": "public_s"}, 200, 5),
    ({"indexName": "public_s", "index_name": "public_s"}, 200, 5),
    ({"indexName": "public_p", "index_name": "public_s"}, 422, None),
])
def test_empty_and_alias_requests(count_service, payload, expected_status, expected_count):
    service, _, clients = count_service
    original = copy.deepcopy(payload)
    response = asyncio.run(post_query(service, "/get_from_type_count", payload))
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json() == {"success": True, "count": expected_count, "message": ""}
    assert payload == original
    if expected_count != 5:
        assert all(not client.count.called for client in clients.values())
    assert_no_index_writes(clients)


@pytest.mark.parametrize("params", [
    {"index_name": "a,b"}, {"index_name": "*"}, {"index_name": "a?"},
    {"index_name": "_all"}, {"index_name": " name"}, {"index_name": 123},
    {"index_name": "."}, {"index_name": ".."}, {"index_name": "-mercado_local"},
    {"index_name": "+mercado_local"}, {"index_name": "_hidden"},
    {"index_name": "cluster:mercado_local"}, {"index_name": "path/index"},
    {"index_name": "a" * 256}, {"index_name": "中" * 86},
    {"from_type": None}, {"from_type": ""}, {"from_type": 42},
    {"start": "2026-09-01"}, {"end": "2026-09-01T00:00:00+08:00"},
    {"start": "2026-02-30 00:00:00"}, {"end": 1790841599},
    {"del_flag": 0},
])
def test_invalid_count_request(count_service, params):
    service, _, clients = count_service
    response = asyncio.run(post_query(service, "/get_from_type_count", dict({"index_name": "public_s"}, **params)))
    assert response.status_code == 422
    assert all(not client.count.called for client in clients.values())
    assert_no_index_writes(clients)


@pytest.mark.parametrize("suffix,provider", [("s", "serverless"), ("p", "paas")])
@pytest.mark.parametrize("bad", [
    KeyError("missing_index"), RuntimeError("transport failure"),
    {"count": 100, "_shards": {"total": 2, "successful": 1, "failed": 1}},
    {"count": 100, "_shards": {"total": 2, "successful": 1, "failed": 0}},
    {"count": 100}, {"_shards": COMPLETE["_shards"]},
    {"count": -1, "_shards": COMPLETE["_shards"]},
    {"count": True, "_shards": COMPLETE["_shards"]},
    dict(COMPLETE, timed_out=True),
    {"count": 4, "_shards": {"total": 0, "successful": 0, "failed": 0}},
    {"count": 4, "_shards": {"total": 1, "successful": 1, "failed": 0, "failures": [{"reason": "failed"}]}},
    {"count": 0, "_shards": {"total": 0, "successful": 0, "failed": 0}},
    dict(COMPLETE, failures=[{"reason": "failed"}]),
    dict(COMPLETE, terminated_early=True),
    dict(COMPLETE, timed_out=None),
])
def test_native_count_failures(count_service, suffix, provider, bad, monkeypatch, caplog):
    service, engine, clients = count_service
    monkeypatch.setattr("kdb.retrieval.engines.es8_search_interface._SHARD_RETRY_BACKOFF", 0)
    clients[provider].count = Mock(side_effect=bad) if isinstance(bad, Exception) else Mock(return_value=bad)
    before = copy.deepcopy(engine.has_build_index)
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "missing_" + suffix}))
    assert response.status_code == 200
    assert response.json()["success"] is False and response.json()["count"] == 0
    assert "get_from_type_count failed" in caplog.text
    assert clients[provider].count.call_args.kwargs["index"] == "missing_" + suffix
    assert engine.has_build_index == before
    assert_no_index_writes(clients)


@pytest.mark.parametrize("count", [0, 12001])
def test_exact_large_count(count_service, count):
    service, _, clients = count_service
    clients["serverless"].count.return_value = dict(COMPLETE, count=count)
    clients["serverless"].count.side_effect = None
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "public_s"}))
    assert response.json() == {"success": True, "count": count, "message": ""}
    assert_no_index_writes(clients)


@pytest.mark.parametrize("suffix,provider", [("s", "serverless"), ("p", "paas")])
def test_count_retry_recovers_complete_response(count_service, suffix, provider, monkeypatch):
    service, _, clients = count_service
    monkeypatch.setattr("kdb.retrieval.engines.es8_search_interface._SHARD_RETRY_BACKOFF", 0)
    clients[provider].count = Mock(side_effect=[
        {"count": 1, "_shards": {"total": 2, "successful": 1, "failed": 1}},
        dict(COMPLETE, count=5),
    ])
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "public_" + suffix}))
    assert response.json() == {"success": True, "count": 5, "message": ""}
    assert clients[provider].count.call_count == 2
    assert_no_index_writes(clients)


@pytest.mark.parametrize("version,kind", [("es7", _engines_providers_es7.EsSearchInterfaceOri), ("opensearch2", _engines_providers_opensearch2.EsSearchInterfaceOpen)])
def test_es7_and_opensearch_count_contract(count_service, monkeypatch, version, kind):
    service, _, clients = count_service
    client = clients["serverless"]
    client.info = Mock(return_value={"version": {"number": "7.10.0"}})
    monkeypatch.setattr(_engines_providers_es7 if version == "es7" else _engines_providers_opensearch2, "Elasticsearch", Mock(return_value=client))
    factory = factories.EsSearchInterface(hosts=["http://fake.invalid:9200"], index_name="public_s",
        vector_fields={"indexes_embedding": 3}, es_version=version,
        extra_params={"auto_update_mapping": False})
    assert isinstance(factory._impl, kind)
    retrieval_runtime.SEARCH_DATA_INTERFACE.engine = factory
    # Capture endpoint calls independently of constructor mapping checks.
    client.create_requests.clear()
    client.indices.put_mapping.reset_mock()
    client.calls.clear()
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "public_s"}))
    assert response.json() == {"success": True, "count": 5, "message": ""}
    assert client.count.call_args.kwargs == {"index": "public_s", "body": {"query": {
        "bool": {"filter": [{"term": {"quality_level": "high"}}, {"term": {"from_type": "chat_auto"}}]}}}}
    partial_response = {"count": 3, "_shards": {"total": 2, "successful": 1, "failed": 1}}
    client.count = Mock(return_value=partial_response)
    assert factory.count_by_query("public_s", {"match_all": {}}) == 3  # preserve pre-existing default
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "public_s"}))
    assert response.json()["success"] is False and response.json()["count"] == 0
    client.count = Mock(side_effect=RuntimeError("missing_index"))
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "missing_s"}))
    assert response.json()["success"] is False and response.json()["count"] == 0
    assert_no_index_writes(clients)


def test_uninitialized_count_service(count_service):
    service, _, clients = count_service
    retrieval_runtime.SEARCH_DATA_INTERFACE = None
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": "public_s"}))
    assert response.json()["success"] is False and response.json()["count"] == 0
    response = asyncio.run(post_query(service, "/get_from_type_count", {"index_name": ""}))
    assert response.json() == {"success": True, "count": 0, "message": ""}
    assert_no_index_writes(clients)
