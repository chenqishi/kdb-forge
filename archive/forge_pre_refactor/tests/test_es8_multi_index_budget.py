"""Each logical index retains its candidates and result identity."""

import copy

import pytest

from kdb.api.search_routes import _shape_search_result
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


class RankedClient:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        route = "vector" if "knn" in str(kwargs["query"]) else "bm25"
        hits = []
        total = 0
        for index in kwargs["index"].split(","):
            rank = {"market_a": 3, "market_b": 2, "payoneer": 1}[index]
            total += {"market_a": {"bm25": 10, "vector": 7},
                      "market_b": {"bm25": 20, "vector": 22},
                      "payoneer": {"bm25": 30, "vector": 26}}[index][route]
            for doc_id in ("shared", f"{route}-only"):
                hits.append({"_index": index, "_id": doc_id, "_score": float(rank),
                             "_source": {"title": f"{index} {doc_id}", "content": "answer",
                                         "title_embedding": [1.0, 0.0, 0.0],
                                         "content_embedding": [1.0, 0.0, 0.0],
                                         "provider": self.provider}})
        # A shared request spends its entire budget on market_a. Separate
        # requests must still return market_b's candidates with the same IDs.
        hits.sort(key=lambda hit: hit["_score"], reverse=True)
        return {"hits": {"total": {"value": total}, "hits": hits[:kwargs["size"]]}}


@pytest.mark.parametrize("indices, expected_total", [
    (["market_a", "market_b"], 32),
    (["market_a", "market_b", "payoneer"], 62),
])
def test_dual_candidates_are_budgeted_per_index_across_provider_groups(indices, expected_total):
    clients = {}

    def factory(config):
        provider = config["hosts"][0]
        clients[provider] = RankedClient(provider)
        return clients[provider]

    router = IndexClientRouter(config={
        "providers": {"serverless": {"hosts": ["serverless"]}, "paas": {"hosts": ["paas"]}},
        "default_provider": "serverless", "index_routes": {"payoneer": "paas"},
    }, client_factory=factory)
    engine = RoutedLegacyEngine(router=router, index_name="market_a",
                                vector_fields={"indexes_embedding": 3}, ensure_index=False)
    docs, total = engine.search_multi({"query": "question", "vector": {"value": [1.0, 0.0, 0.0]}},
                                      index_names=indices, size=4)
    assert total == expected_total  # Sum each index's max(bm25, vector) total.
    identities = [(doc["_index"], doc["_id"]) for doc in docs]
    assert len(identities) == len(set(identities)) == len(indices) * 3
    for index in indices:
        assert {doc_id for hit_index, doc_id in identities if hit_index == index} == {
            "shared", "bm25-only", "vector-only",
        }
    calls = [call for client in clients.values() for call in client.calls]
    assert len(calls) == len(indices) * 2
    assert all(call["size"] == 2 and "," not in call["index"] for call in calls)
    assert {call["index"] for call in clients["serverless"].calls} == {"market_a", "market_b"}
    if "payoneer" in indices:
        assert {call["index"] for call in clients["paas"].calls} == {"payoneer"}
    # Missing dataset still identifies the logical knowledge base at /search.
    for doc in docs:
        doc["similarity"] = 0.9
        assert _shape_search_result(doc)["dataset"] == doc["_index"]


def test_hit_identity_is_preserved_and_explicit_dataset_is_not_replaced():
    hits = {"hits": {"hits": [
        {"_index": "market_a", "_id": "same", "_score": 2.0,
         "_source": {"title": "question", "content": "answer"}},
        {"_index": "market_b", "_id": "same", "_score": 1.0,
         "_source": {"title": "question", "content": "answer", "dataset": "customer-defined"}},
    ]}}
    docs = RoutedLegacyEngine._hits(hits)
    assert [(doc["_index"], doc["_id"]) for doc in docs] == [("market_a", "same"), ("market_b", "same")]
    assert [_shape_search_result(doc)["dataset"] for doc in docs] == ["market_a", "customer-defined"]
