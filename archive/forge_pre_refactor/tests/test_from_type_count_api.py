"""Real API/Service/Repository/Engine counts with only the ES client replaced."""

import copy
import json
import logging
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from kdb.api import search_routes
from kdb.api.app import app as full_app
from kdb.api.retrieval_app import app
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


DOCUMENTS = {
    "mercado_local": [
        {"quality_level": "high", "from_type": "chat_auto", "insert_time": "2026-09-01 00:00:00", "del_flag": 1, "audit_result": -1, "data_type": "segment"},
        {"quality_level": "high", "from_type": "chat_auto", "insert_time": "2026-09-30 23:59:59", "del_flag": 0, "audit_result": 0},
        {"quality_level": "high", "from_type": "chat_auto", "insert_time": "2026-10-01 00:00:00"},
        {"quality_level": "high", "from_type": "chat_auto"},
        {"quality_level": "low", "from_type": "chat_auto", "insert_time": "2026-09-15 12:00:00"},
        {"quality_level": "high", "from_type": "document", "insert_time": "2026-09-15 12:00:00"},
        {"quality_level": "high", "from_type": "normal_chat", "from_type_norm": "chat_auto"},
        {"quality_level": "high", "from_type": "Chat_auto"},
    ],
    "payoneer_olive": [
        {"quality_level": "high", "from_type": "chat_auto", "del_flag": 1, "audit_result": -1},
        {"quality_level": "high", "from_type": "document", "insert_time": "2026-09-01 00:00:00"},
    ],
}


class ClientError(Exception):
    def __init__(self, status_code=503):
        self.status_code = status_code
        super().__init__("provider-password=do-not-expose")


def complete_count(number):
    return {"count": number, "_shards": {"total": 2, "successful": 2, "skipped": 0, "failed": 0}}


def count_rows(rows, query):
    """Evaluate the external count server's supported term/range DSL generically."""
    def matches(row, clause):
        if "term" in clause:
            return all(row.get(field) == value for field, value in clause["term"].items())
        if "range" in clause:
            for field, bounds in clause["range"].items():
                value = row.get(field)
                if value is None or value < bounds["gte"] or value > bounds["lte"]:
                    return False
            return True
        raise AssertionError("unexpected count query clause")

    return sum(all(matches(row, clause) for clause in query["bool"]["filter"]) for row in rows)


@pytest.fixture
def stack(monkeypatch):
    clients = {}
    calls = []

    def factory(config):
        provider = config["hosts"][0]
        client = Mock()
        client.search.side_effect = AssertionError("count must not retrieve documents")
        client.indices.create.side_effect = AssertionError("count must not create an index")
        client.indices.put_mapping.side_effect = AssertionError("count must not change mapping")

        def count(**kwargs):
            calls.append({"provider": provider, **copy.deepcopy(kwargs)})
            name = kwargs["index"]
            if name not in DOCUMENTS:
                raise ClientError(404)
            return complete_count(count_rows(DOCUMENTS[name], kwargs["query"]))

        client.count.side_effect = count
        clients[provider] = client
        return client

    router = IndexClientRouter(config={
        "providers": {"serverless": {"hosts": ["serverless"]}, "paas": {"hosts": ["paas"]}},
        "default_provider": "serverless", "index_routes": {"*payoneer*": "paas"},
    }, client_factory=factory)
    engine = RoutedLegacyEngine(router=router, index_name="mercado_local", ensure_index=False,
                                vector_fields={"indexes_embedding": 4})
    embedding = Mock()
    embedding.text2embedding.side_effect = AssertionError("count must not generate embeddings")
    service = KnowledgeService(KnowledgeRepository(engine=engine), embedding)
    monkeypatch.setattr(search_routes, "_count_service", service)
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "test-user")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "test-pass")
    monkeypatch.delenv("KDB_SEARCH_ALLOW_LOOPBACK", raising=False)
    yield {"service": service, "engine": engine, "router": router, "clients": clients,
           "calls": calls, "embedding": embedding, "client": TestClient(app)}
    embedding.text2embedding.assert_not_called()
    for client in clients.values():
        client.search.assert_not_called()
        client.indices.create.assert_not_called()
        client.indices.put_mapping.assert_not_called()
    router.close()


def post(stack, body, application=None):
    client = TestClient(application) if application else stack["client"]
    return client.post("/get_from_type_count", json=body, auth=("test-user", "test-pass"))


@pytest.mark.parametrize("application", [app, full_app])
@pytest.mark.parametrize("index,expected,provider", [("mercado_local", 4, "serverless"), ("payoneer_olive", 1, "paas")])
def test_defaults_reach_real_service_engine_and_requested_provider(stack, application, index, expected, provider):
    response = post(stack, {"index_name": index}, application)
    assert response.status_code == 200
    assert response.json() == {"success": True, "count": expected, "message": ""}
    assert stack["calls"] == [{"provider": provider, "index": index,
        "query": {"bool": {"filter": [{"term": {"quality_level": "high"}}, {"term": {"from_type": "chat_auto"}}]}},
        "allow_no_indices": False, "ignore_unavailable": False, "expand_wildcards": "none"}]


@pytest.mark.parametrize("source,expected", [("chat_auto", 4), ("document", 1), ("normal_chat", 1), ("Chat_auto", 1), (" chat_auto ", 0), ("absent_source", 0)])
def test_source_values_are_exact_without_norm_or_other_business_filters(stack, source, expected):
    response = post(stack, {"index_name": "mercado_local", "from_type": source})
    assert response.json() == {"success": True, "count": expected, "message": ""}
    assert stack["calls"][0]["query"]["bool"]["filter"] == [
        {"term": {"quality_level": "high"}}, {"term": {"from_type": source}},
    ]


@pytest.mark.parametrize("times,expected", [
    ({}, 4), ({"start": None, "end": None}, 4),
    ({"start": "2026-09-01 00:00:00"}, 4), ({"end": "2026-09-30 23:59:59"}, 4),
    ({"start": "2026-09-01 00:00:00", "end": "2026-09-30 23:59:59"}, 2),
    ({"start": "2026-09-01 00:00:00", "end": "2026-09-01 00:00:00"}, 1),
    ({"start": "2026-09-30 23:59:59", "end": "2026-09-30 23:59:59"}, 1),
    ({"start": "2026-10-01 00:00:00", "end": "2026-09-01 00:00:00"}, 0),
    ({"start": "0001-01-01 00:00:00", "end": "0001-12-31 23:59:59"}, 0),
])
def test_time_ranges_preserve_single_sided_and_inclusive_behavior(stack, times, expected):
    response = post(stack, {"index_name": "mercado_local", **times})
    assert response.json() == {"success": True, "count": expected, "message": ""}
    clauses = stack["calls"][0]["query"]["bool"]["filter"]
    if times.get("start") is not None and times.get("end") is not None:
        assert clauses[-1] == {"range": {"insert_time": {"gte": times["start"], "lte": times["end"]}}}
    else:
        assert len(clauses) == 2


@pytest.mark.parametrize("body", [{}, {"index_name": None}, {"index_name": ""}, {"indexName": ""}, {"index_name": None, "indexName": None}])
def test_empty_index_returns_success_zero_without_initialization(stack, body, monkeypatch):
    monkeypatch.setattr(search_routes, "_count_service", None)
    initial = Mock(side_effect=AssertionError("empty index must not initialize service"))
    monkeypatch.setattr(KnowledgeService, "from_count_config", initial)
    assert post(stack, body).json() == {"success": True, "count": 0, "message": ""}
    assert not stack["calls"]
    initial.assert_not_called()


@pytest.mark.parametrize("body", [
    {"indexName": "mercado_local"}, {"index_name": "mercado_local", "indexName": "mercado_local"},
])
def test_java_index_alias_is_supported(stack, body):
    assert post(stack, body).json()["count"] == 4
    assert stack["calls"][0]["index"] == "mercado_local"


@pytest.mark.parametrize("body", [
    {"index_name": "mercado_local", "indexName": "payoneer_olive"},
    {"index_name": None, "indexName": "mercado_local"},
    *[{"index_name": index} for index in [[], 3, True, "a,b", "*", "a?", "_all", " ", "a b", "a/b", "<dated-index>", "-a", "cluster:a"]],
    *[{"index_name": "mercado_local", "from_type": source} for source in [None, "", 3, [], True]],
    *[{"index_name": "mercado_local", "start": time} for time in ["", "2026-09-01", "2026-09-01T00:00:00Z", "2026-9-01 00:00:00", "2026-02-30 00:00:00", "2026-09-01 24:00:00", 3]],
    {"index_name": "", "end": "invalid"}, {"index_name": "", "from_type": None},
    *[{"index_name": "mercado_local", field: value} for field, value in [
        ("del_flag", 0), ("audit_result", [1, 2]), ("data_type", "qa"),
        ("category", "other"), ("quality_level", "low"), ("from_type_norm", "chat_auto"),
    ]],
])
def test_invalid_requests_are_422_without_any_es_count(stack, body):
    assert post(stack, body).status_code == 422
    assert not stack["calls"]


@pytest.mark.parametrize("number", [0, 8, 10000, 20001])
def test_native_counts_are_not_search_hit_lower_bounds(stack, number):
    client = stack["router"].get_client_by_index("mercado_local")
    client.count.side_effect = None
    client.count.return_value = complete_count(number)
    assert post(stack, {"index_name": "mercado_local"}).json() == {"success": True, "count": number, "message": ""}


def test_missing_index_is_failure_zero_without_creating_it(stack):
    response = post(stack, {"index_name": "missing_original"})
    assert response.status_code == 200
    assert response.json() == {"success": False, "count": 0, "message": "统计失败"}
    assert stack["calls"][0]["index"] == "missing_original"


@pytest.mark.parametrize("failure", [ClientError(401), ClientError(503), TimeoutError("do-not-expose")])
def test_external_failures_are_zero_and_do_not_leak_details(stack, failure, caplog):
    stack["router"].get_client_by_index("mercado_local").count.side_effect = failure
    with caplog.at_level(logging.WARNING):
        response = post(stack, {"index_name": "mercado_local"})
    assert response.status_code == 200 and response.json() == {"success": False, "count": 0, "message": "统计失败"}
    assert "do-not-expose" not in response.text and "do-not-expose" not in caplog.text


@pytest.mark.parametrize("payload", [
    {"_shards": {"total": 1, "successful": 1, "failed": 0}},
    complete_count(-1), complete_count(True), complete_count("4"), complete_count(4.0),
    {"count": 4}, {"count": 4, "_shards": None},
    {"count": 4, "_shards": {"total": 2, "successful": 1, "failed": 0}},
    {"count": 4, "_shards": {"total": 2, "successful": 1, "failed": 1}},
    {"count": 4, "_shards": {"total": 0, "successful": 0, "failed": 0}},
    {"count": 4, "_shards": {"total": True, "successful": 1, "failed": 0}},
    {"count": 4, "_shards": {"total": 1, "successful": 1, "failed": 0,
                           "failures": [{"reason": "provider-password=do-not-expose"}]}},
    {**complete_count(4), "timed_out": True},
])
def test_incomplete_or_malformed_native_counts_are_failure_zero(stack, payload, caplog):
    client = stack["router"].get_client_by_index("mercado_local")
    client.count.side_effect = None
    client.count.return_value = payload
    with caplog.at_level(logging.WARNING):
        response = post(stack, {"index_name": "mercado_local"})
    assert response.status_code == 200
    assert response.json() == {"success": False, "count": 0, "message": "统计失败"}
    assert "do-not-expose" not in response.text and "do-not-expose" not in caplog.text


@pytest.mark.parametrize("body", [{"index_name": "mercado_local"}, {"index_name": ""}])
def test_existing_auth_also_protects_empty_count_requests(stack, body):
    response = stack["client"].post("/get_from_type_count", json=body)
    assert response.status_code == 401
    assert not stack["calls"]


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_count_uses_existing_opt_in_direct_loopback_auth(stack, monkeypatch, host):
    client = TestClient(app, client=(host, 50000))
    assert client.post("/get_from_type_count", json={"index_name": "mercado_local"}).status_code == 401
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    assert client.post("/get_from_type_count", json={"index_name": "mercado_local"}).json() == {
        "success": True, "count": 4, "message": ""}


@pytest.mark.parametrize("headers,auth", [
    ({"X-Forwarded-For": "127.0.0.1"}, None),
    ({"Forwarded": "for=127.0.0.1"}, None),
    ({"Authorization": "Bearer invalid"}, None),
    ({}, ("test-user", "wrong")),
])
def test_loopback_does_not_bypass_proxy_or_invalid_credentials(stack, monkeypatch, headers, auth):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post("/get_from_type_count", json={"index_name": "mercado_local"},
                           headers=headers, auth=auth)
    assert response.status_code == 401
    assert not stack["calls"]


def test_missing_auth_config_is_503_without_es(stack, monkeypatch):
    monkeypatch.delenv("KDB_SEARCH_BASIC_PASSWORD")
    assert post(stack, {"index_name": "mercado_local"}).status_code == 503
    assert not stack["calls"]


def test_count_factory_disables_configured_ensure_and_never_loads_embedding(stack, monkeypatch, tmp_path):
    config = tmp_path / "engine.json"
    config.write_text(json.dumps({"es_version": "8.17", "hosts": ["serverless"], "index_name": "default_missing",
        "vector_fields": {"indexes_embedding": 4},
        "extra_params": {"ensure_index_on_init": True}}))
    runtime = tmp_path / "runtime.json"
    runtime.write_text(json.dumps({"engine_config_path": str(config), "embedding_config_path": "/never/read/embedding.json", "legacy_search_config_path": "/never/read/legacy.json"}))
    external = stack["router"].get_client_by_index("mercado_local")
    monkeypatch.setattr(IndexClientRouter, "_create_client", lambda self, cfg: external)
    import kdb.crud.service as service_module
    build = Mock(side_effect=AssertionError("count initialization must not load embedding"))
    monkeypatch.setattr(service_module, "build_embedding_client", build)
    monkeypatch.setenv("KDB_FORGE_CONFIG", str(runtime))
    monkeypatch.setattr(search_routes, "_count_service", None)
    response = post(stack, {"index_name": "mercado_local"})
    assert response.json() == {"success": True, "count": 4, "message": ""}
    initialized = search_routes._count_service
    assert isinstance(initialized, KnowledgeService)
    assert isinstance(initialized._repo._engine, RoutedLegacyEngine)
    assert initialized._repo._engine._ensure_index_on_init is False
    assert initialized._embedding is None
    build.assert_not_called()
    external.indices.exists.assert_not_called()
    external.indices.get_mapping.assert_not_called()


def test_initialization_failure_is_observable_and_zero(stack, monkeypatch, caplog):
    monkeypatch.setattr(search_routes, "_count_service", None)
    monkeypatch.setattr(KnowledgeService, "from_count_config", Mock(side_effect=ClientError(503)))
    with caplog.at_level(logging.WARNING):
        response = post(stack, {"index_name": "mercado_local"})
    assert response.status_code == 200 and response.json() == {"success": False, "count": 0, "message": "统计失败"}
    assert "initialization failed" in caplog.text and "do-not-expose" not in caplog.text
    assert not stack["calls"]
