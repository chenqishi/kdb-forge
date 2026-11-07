"""Opt-in shard-copy preference and DFS preserve retrieval budgets and routing."""

import copy
import re
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
from elastic_transport import ApiResponseMeta, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse

from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


QUERY = {
    "query": "question α",
    "vector": {"value": [1.0, 0.0, 0.0]},
    "attribute": [{"data_type": "segment", "audit_result": [1, 2, -1]}],
    "insert_time": ["2026-09-01", "2026-09-02"],
    "update_time": ["2026-09-01", None],
}


class CopyClient:
    """Unpinned requests alternate copies; a custom preference pins the copy."""

    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        preference = kwargs.get("preference")
        copy_id = int(preference[-1], 16) % 2 if preference else len(self.calls) % 2
        return {"hits": {"total": {"value": 1}, "hits": [{
            "_index": kwargs["index"], "_id": f"copy-{copy_id}", "_score": 1.0,
            "_source": {"title": "answer", "content": "answer",
                        "title_embedding": [1.0, 0.0, 0.0],
                        "content_embedding": [1.0, 0.0, 0.0]},
        }]}}


def make_engine(extra=None, default_provider="serverless", sdk=False):
    clients = {}

    def factory(config):
        client = CopyClient()
        clients[config["hosts"][0]] = client
        return client

    router = IndexClientRouter(config={
        "providers": {"serverless": {"hosts": ["http://serverless.example:9200"]},
                      "paas": {"hosts": ["http://paas.example:9200"]}},
        "default_provider": default_provider,
        "index_routes": {"payoneer": "paas"},
    }, **({} if sdk else {"client_factory": factory}))
    engine = RoutedLegacyEngine(router=router, index_name="market_a",
                                vector_fields={"indexes_embedding": 3},
                                extra_params=extra, ensure_index=False)
    return engine, clients


def calls_for(clients, index="market_a"):
    return [call for client in clients.values() for call in client.calls if call["index"] == index]


def test_text_service_uses_same_preference_for_both_routes_and_reembedding_noise():
    engine, clients = make_engine({"stable_query_preference": True})
    vectors = iter((np.array([1.0, 0.0, 0.0]), np.array([1.0, 1e-10, 0.0])))

    class Embedding:
        def text2embedding(self, _text):
            return next(vectors)

    service = KnowledgeService(KnowledgeRepository(engine=engine), Embedding())
    conditions = [{"data_type": "segment"}]
    first, _ = service.search_text("question α", condition_dicts=copy.deepcopy(conditions), size=10)
    second, _ = service.search_text("question α", condition_dicts=copy.deepcopy(conditions), size=10)
    calls = calls_for(clients)
    assert len(calls) == 4 and len({call["preference"] for call in calls}) == 1
    preference = calls[0]["preference"]
    assert re.fullmatch(r"kdb-query-v1-[0-9a-f]{64}", preference)
    assert "question α" not in preference
    assert [doc["_id"] for doc in first] == [doc["_id"] for doc in second]
    assert len(first) == len(second) == 1  # Both routes selected the same copy.
    assert all(call["size"] == 10 for call in calls)


@pytest.mark.parametrize("change", [
    {"query": "another question"},
    {"fields": {"title": "different field query"}},
    {"attribute": [{"data_type": "qa", "audit_result": [1, 2]}]},
    {"insert_time": ["2026-09-02", "2026-09-03"]},
    {"update_time": ["2026-09-02", None]},
])
def test_original_text_fields_conditions_and_time_scope_change_preference(change):
    engine, clients = make_engine({"stable_query_preference": True})
    original = copy.deepcopy(QUERY)
    engine.search_multi(original, size=20)
    changed = copy.deepcopy(QUERY)
    changed.update(change)
    engine.search_multi(changed, size=20)
    before_bm25, before_vector, after_bm25, after_vector = calls_for(clients)
    assert before_bm25["preference"] == before_vector["preference"]
    assert after_bm25["preference"] == after_vector["preference"]
    assert before_bm25["preference"] != after_bm25["preference"]
    assert original == QUERY


def test_canonical_object_key_order_does_not_change_preference():
    engine, clients = make_engine({"stable_query_preference": True})
    engine.search_multi(copy.deepcopy(QUERY), size=20)
    reordered = {key: copy.deepcopy(value) for key, value in reversed(list(QUERY.items()))}
    reordered["attribute"][0] = {"audit_result": [1, 2, -1], "data_type": "segment"}
    engine.search_multi(reordered, size=20)
    assert len({call["preference"] for call in calls_for(clients)}) == 1


def test_index_and_provider_scopes_have_distinct_preferences():
    engine, clients = make_engine({"stable_query_preference": True})
    engine.search_multi(copy.deepcopy(QUERY), index_names=["market_a", "market_b", "payoneer"], size=20)
    preferences = {}
    for index in ("market_a", "market_b", "payoneer"):
        calls = calls_for(clients, index)
        assert len(calls) == 2 and calls[0]["preference"] == calls[1]["preference"]
        preferences[index] = calls[0]["preference"]
    assert len(set(preferences.values())) == 3
    assert {call["index"] for call in clients["http://serverless.example:9200"].calls} == {"market_a", "market_b"}
    assert {call["index"] for call in clients["http://paas.example:9200"].calls} == {"payoneer"}
    other_engine, other_clients = make_engine({"stable_query_preference": True}, default_provider="paas")
    other_engine.search_multi(copy.deepcopy(QUERY), size=20)
    assert calls_for(other_clients)[0]["preference"] != preferences["market_a"]


def test_fields_queries_are_pinned_and_raw_vector_only_keeps_default():
    engine, clients = make_engine({"stable_query_preference": True})
    engine.search_multi({"fields": {"title": "field query"}, "vector": QUERY["vector"]}, size=20)
    assert len({call["preference"] for call in calls_for(clients)}) == 1
    engine.search_multi({"vector": QUERY["vector"], "attribute": QUERY["attribute"]}, size=20)
    assert "preference" not in calls_for(clients)[-1]


@pytest.mark.parametrize("extra", [None, {"stable_query_preference": False}, {"retrieval_search_types": None}])
def test_default_options_do_not_change_client_requests(extra):
    engine, clients = make_engine(extra)
    engine.search_multi(copy.deepcopy(QUERY), size=20)
    calls = calls_for(clients)
    assert len(calls) == 2
    assert all("preference" not in call and "search_type" not in call for call in calls)


def test_options_preserve_query_budgets_missing_tolerance_and_vector_hydration():
    default, default_clients = make_engine()
    enabled, enabled_clients = make_engine({"stable_query_preference": True,
                                           "retrieval_search_types": {"market_a": "dfs_query_then_fetch"}})
    default.search_multi(copy.deepcopy(QUERY), size=20)
    enabled.search_multi(copy.deepcopy(QUERY), size=20)
    for before, after in zip(calls_for(default_clients), calls_for(enabled_clients)):
        assert {key: value for key, value in after.items() if key not in ("preference", "search_type")} == before
        assert after["ignore_unavailable"] is True and after["allow_no_indices"] is True
        assert after["docvalue_fields"] == ["title_embedding", "content_embedding"]
    knn = calls_for(enabled_clients)[1]["query"]["bool"]["should"][0]["nested"]["query"]["knn"]
    assert (knn["k"], knn["num_candidates"], knn["boost"]) == (10, 100, 2.0)


@pytest.mark.parametrize("search_type", ["query_then_fetch", "dfs_query_then_fetch"])
def test_per_index_search_type_both_routes_preserves_other_indices_and_providers(search_type):
    engine, clients = make_engine({"retrieval_search_types": {"market_a": search_type, "payoneer": search_type}})
    docs, total = engine.search_multi(copy.deepcopy(QUERY), index_names=["market_a", "market_b", "payoneer"], size=20)
    assert total == 3 and {doc["_index"] for doc in docs} == {"market_a", "market_b", "payoneer"}
    for index in ("market_a", "payoneer"):
        assert len(calls_for(clients, index)) == 2
        assert all(call["search_type"] == search_type and "preference" not in call for call in calls_for(clients, index))
    assert all("search_type" not in call and "preference" not in call for call in calls_for(clients, "market_b"))


@pytest.mark.parametrize("bad", [1, 0, "true", None])
def test_preference_flag_requires_strict_bool(bad):
    with pytest.raises(ValueError, match="stable_query_preference"):
        make_engine({"stable_query_preference": bad})


@pytest.mark.parametrize("bad", [True, [], "dfs_query_then_fetch"])
def test_search_type_option_requires_mapping_or_none(bad):
    with pytest.raises(ValueError, match="retrieval_search_types"):
        make_engine({"retrieval_search_types": bad})


@pytest.mark.parametrize("bad", [None, False, "dfs", "DFS_QUERY_THEN_FETCH"])
def test_search_type_mapping_rejects_unknown_enum(bad):
    with pytest.raises(ValueError, match="retrieval_search_types"):
        make_engine({"retrieval_search_types": {"market_a": bad}})


@pytest.mark.parametrize("bad", ["", "Market_A", " market_a", "market_*", "market_a,market_b", 1])
def test_search_type_mapping_requires_exact_normalized_index_name(bad):
    with pytest.raises(ValueError, match="retrieval_search_types"):
        make_engine({"retrieval_search_types": {bad: "dfs_query_then_fetch"}})


def test_real_es817_client_serializes_optional_preference_and_search_type(monkeypatch):
    calls = []

    def request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        parsed = urlsplit(target)
        calls.append({"host": node.host, "params": parse_qs(parsed.query), "body": copy.deepcopy(body)})
        return TransportApiResponse(ApiResponseMeta(200, "1.1", HttpHeaders({"x-elastic-product": "Elasticsearch"}), 0, node),
                                    {"hits": {"total": {"value": 0}, "hits": []}})

    monkeypatch.setattr(Transport, "perform_request", request)
    engine, _ = make_engine({"stable_query_preference": True,
                             "retrieval_search_types": {"market_a": "dfs_query_then_fetch"}}, sdk=True)
    try:
        engine.search_multi(copy.deepcopy(QUERY), size=20)
    finally:
        engine.router.close()
    assert len(calls) == 2
    assert calls[0]["params"]["preference"] == calls[1]["params"]["preference"]
    assert all(call["params"]["search_type"] == ["dfs_query_then_fetch"] for call in calls)
    assert all(call["params"]["ignore_unavailable"] == ["true"]
               and call["params"]["allow_no_indices"] == ["true"] for call in calls)
