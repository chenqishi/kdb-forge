"""Optional missing indices stay empty; actual provider failures stay errors."""

import copy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
from elastic_transport import ApiResponseMeta, ConnectionError, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse
from fastapi.testclient import TestClient

from kdb.api import search_routes
from kdb.api.retrieval_app import app
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


@pytest.fixture
def search_stack(monkeypatch):
    state = SimpleNamespace(calls=[], failures={})
    existing = {"serverless.example": {"market_a"}, "paas.example": {"payoneer"}}

    def perform_request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        assert url.path.endswith("/_search")
        names = url.path.strip("/").split("/")[0].split(",")
        params = parse_qs(url.query)
        state.calls.append({"host": node.host, "indices": names, "params": params,
                            "body": copy.deepcopy(body)})
        failure = next((state.failures[name] for name in names if name in state.failures), None)
        if failure == "connection":
            raise ConnectionError("provider connection failed")
        if failure is not None:
            status, error_type = failure
            response = {"error": {"type": error_type, "reason": "provider failure"},
                        "status": status}
        else:
            available = [name for name in names if name in existing[node.host]]
            missing_allowed = (params.get("ignore_unavailable") == ["true"]
                               and params.get("allow_no_indices") == ["true"])
            if len(available) != len(names) and not missing_allowed:
                status = 404
                response = {"error": {"type": "index_not_found_exception", "reason": "missing index"},
                            "status": status}
            else:
                status = 200
                response = {"hits": {"total": {"value": len(available)}, "hits": [
                    {"_index": name, "_id": "shared", "_score": 1.0,
                     "_source": {"title": "question", "content": "answer",
                                 "title_embedding": [1.0, 0.0, 0.0],
                                 "content_embedding": [1.0, 0.0, 0.0]}}
                    for name in available
                ]}}
        return TransportApiResponse(
            ApiResponseMeta(status, "1.1", HttpHeaders({"x-elastic-product": "Elasticsearch"}), 0, node),
            response,
        )

    monkeypatch.setattr(Transport, "perform_request", perform_request)
    router = IndexClientRouter(config={
        "providers": {
            "serverless": {"hosts": ["http://serverless.example:9200"], "max_retries": 0},
            "paas": {"hosts": ["http://paas.example:9200"], "max_retries": 0},
        },
        "default_provider": "serverless",
        "index_routes": {"payoneer": "paas", "missing_paas": "paas"},
    })
    engine = RoutedLegacyEngine(router=router, index_name="market_a",
                                vector_fields={"indexes_embedding": 3}, ensure_index=False)
    service = KnowledgeService(KnowledgeRepository(engine=engine),
                               SimpleNamespace(text2embedding=lambda _text: np.array([1.0, 0.0, 0.0])))
    monkeypatch.setattr(search_routes, "_service", service)
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "tester")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "secret")
    state.client = TestClient(app)
    state.engine = engine
    yield state
    state.client.close()
    router.close()


@pytest.mark.parametrize("indices, expected", [
    (["private_81927", "market_a"], {"market_a"}),
    (["market_a", "customer_private_missing"], {"market_a"}),
    (["private_81927", "payoneer"], {"payoneer"}),
    (["payoneer", "private_81927"], {"payoneer"}),
    (["market_a", "private_81927", "payoneer"], {"market_a", "payoneer"}),
])
def test_missing_index_first_last_and_cross_provider_keeps_results(indices, expected, search_stack):
    response = search_stack.client.post("/search", auth=("tester", "secret"),
                                        json={"text": "question", "index_names": indices, "top_k": 5})
    assert response.status_code == 200
    results = response.json()["results"]
    assert {doc["dataset"] for doc in results} == expected
    assert len(results) == len(expected)  # Shared ID in different indices remains distinct.
    assert all(call["params"]["ignore_unavailable"] == ["true"]
               and call["params"]["allow_no_indices"] == ["true"]
               for call in search_stack.calls)


@pytest.mark.parametrize("indices", ["customer_private_missing", ["private_81927", "missing_paas"]])
def test_all_missing_indices_return_successful_empty_results(indices, search_stack):
    response = search_stack.client.post("/search", auth=("tester", "secret"),
                                        json={"text": "question", "index_names": indices})
    assert response.status_code == 200
    assert response.json() == {"results": []}


@pytest.mark.parametrize("failure", [
    (403, "security_exception"),
    (400, "query_shard_exception"),
    (503, "unavailable_shards_exception"),
    "connection",
])
def test_permission_mapping_and_transport_failures_are_not_ignored(failure, search_stack):
    search_stack.failures["market_a"] = failure
    response = search_stack.client.post("/search", auth=("tester", "secret"),
                                        json={"text": "question", "index_names": ["market_a", "private_81927"]})
    assert response.status_code == 503
    assert response.json() == {"detail": "检索服务暂不可用"}
