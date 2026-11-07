"""Native candidate scoring retains cosine's weight relative to must scores."""

import copy
import math

import pytest

from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


def _knn(query):
    for clause in query["bool"].get("should", []):
        if "nested" in clause:
            return clause["nested"]["query"].get("knn")
        if "knn" in clause:
            return clause["knn"]
    return None


class ScoreClient:
    """Evaluate native cosine scores with different parent condition scores.

    The rows represent documents whose condition scores differ, for example
    because the keyword term is scored with different shard statistics.
    """

    rows = [
        {"id": "higher-cosine", "vector": [0.8, 0.6, 0.0], "must": 0.1, "bm25": 0.0},
        {"id": "higher-must", "vector": [0.7, math.sqrt(0.51), 0.0], "must": 0.16, "bm25": 2.0},
        {"id": "lexical", "vector": [0.0, 1.0, 0.0], "must": 0.0, "bm25": 20.0},
    ]

    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        knn = _knn(kwargs["query"])
        has_text = any("multi_match" in clause or "match" in clause
                       for clause in kwargs["query"]["bool"].get("should", []))
        hits = []
        for row in self.rows:
            score = row["must"]
            if has_text:
                score += row["bm25"]
            if knn is not None:
                q = knn["query_vector"]
                vector = row["vector"]
                cosine = sum(a * b for a, b in zip(q, vector)) / (
                    math.sqrt(sum(a * a for a in q)) * math.sqrt(sum(b * b for b in vector))
                )
                score += knn.get("boost", 1.0) * (1.0 + cosine) / 2.0
            if score < kwargs.get("min_score", 0.0):
                continue
            hits.append({"_index": kwargs["index"], "_id": row["id"], "_score": score,
                         "_source": {"title": row["id"], "title_embedding": row["vector"],
                                     "indexes": [{"text": row["id"], "embedding": row["vector"]}]}})
        hits.sort(key=lambda hit: hit["_score"], reverse=True)
        return {"hits": {"total": {"value": len(hits)}, "hits": hits[:kwargs["size"]]}}


@pytest.fixture
def engine_and_client():
    client = ScoreClient()
    router = IndexClientRouter(config={"hosts": ["http://fake"]},
                               client_factory=lambda _config: client)
    engine = RoutedLegacyEngine(router=router, index_name="demo",
                                vector_fields={"indexes_embedding": 3}, ensure_index=False)
    return engine, client


QUERY = {"query": "question", "vector": {"value": [1.0, 0.0, 0.0]}}


def test_vector_candidate_route_restores_old_cosine_order(engine_and_client):
    engine, client = engine_and_client
    # Old script_score used raw cosine, so higher-cosine wins: .90 > .86.
    old_order = sorted(ScoreClient.rows,
                       key=lambda row: row["must"] + row["vector"][0], reverse=True)
    assert old_order[0]["id"] == "higher-cosine"
    # Native normalization without correction reverses the winner: 1.01 > 1.
    uncorrected = engine._build_search_query(QUERY, include_text=False)
    baseline = client.search(index="demo", query=uncorrected, size=1)
    assert baseline["hits"]["hits"][0]["_id"] == "higher-must"

    docs, _total = engine.search_multi(QUERY, size=2, recall_mode="dual")
    assert [doc["_id"] for doc in docs] == ["lexical", old_order[0]["id"]]
    bm25_call, vector_call = client.calls[-2:]
    assert _knn(bm25_call["query"]) is None
    knn = _knn(vector_call["query"])
    assert knn["boost"] == 2.0
    assert knn["k"] == 10 and knn["num_candidates"] == 100
    assert vector_call["query"]["bool"]["minimum_should_match"] == 1
    assert len(vector_call["query"]["bool"]["should"]) == 1
    assert vector_call["query"]["bool"]["should"][0]["nested"]["score_mode"] == "max"
    assert bm25_call["size"] == vector_call["size"] == 1
    # The added constant is shared, while the old relative scores are preserved.
    assert docs[-1]["score"] == pytest.approx(old_order[0]["must"] + old_order[0]["vector"][0] + 1.0)


@pytest.mark.parametrize("mode", ["single", "legacy"])
def test_single_mixed_route_preserves_native_scoring(mode, engine_and_client):
    engine, client = engine_and_client
    docs, _total = engine.search_multi(QUERY, size=1, recall_mode=mode)
    assert len(client.calls) == 1
    assert "boost" not in _knn(client.calls[0]["query"])
    assert docs[0]["_id"] == "lexical"
    assert docs[0]["score"] == pytest.approx(20.5)


def test_bm25_mode_preserves_lexical_score(engine_and_client):
    engine, client = engine_and_client
    docs, _total = engine.search_multi(QUERY, size=1, recall_mode="bm25")
    assert _knn(client.calls[0]["query"]) is None
    assert docs[0]["_id"] == "lexical"
    assert docs[0]["score"] == pytest.approx(20.0)


def test_multi_vector_route_keeps_default_boost_and_candidate_budgets(engine_and_client):
    engine, client = engine_and_client
    query = {"query": "question", "vector": [
        {"value": [1.0, 0.0, 0.0]}, {"value": [0.0, 1.0, 0.0]},
    ]}
    engine.search_multi(query, size=4, recall_mode="dual")
    bm25_call, vector_call = client.calls
    assert _knn(bm25_call["query"]) is None
    clauses = vector_call["query"]["bool"]["should"]
    assert len(clauses) == 2
    for clause in clauses:
        knn = clause["nested"]["query"]["knn"]
        assert "boost" not in knn
        assert knn["k"] == 10 and knn["num_candidates"] == 100
        assert clause["nested"]["score_mode"] == "max"
    assert bm25_call["size"] == vector_call["size"] == 2


def test_search_by_vector_return_score_keeps_native_semantics(engine_and_client):
    engine, client = engine_and_client
    results = engine.search_by_vector([1.0, 0.0, 0.0], "indexes_embedding",
                                      size=1, min_score=0.6, return_score=True)
    document, score = results[0]
    assert document["_id"] == "higher-must"
    assert score == pytest.approx(1.01)
    assert "boost" not in _knn(client.calls[0]["query"])
    assert client.calls[0]["min_score"] == 0.6
