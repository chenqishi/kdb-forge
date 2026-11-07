"""Offline contract tests for the isolated Elasticsearch 8.17 adapter.

These tests inject fake provider clients. They validate serialized ES8 requests and
compatibility contracts; they do not claim retrieval quality against a real cluster.
"""

from __future__ import annotations

import json

import pytest

from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8


class FakeIndices:
    def __init__(self, exists=False, mapping=None):
        self.exists_value = exists
        self.mapping = mapping or {}
        self.created = []
        self.refreshes = []
        self.put_mappings = []

    def exists(self, **kwargs):
        return self.exists_value

    def create(self, **kwargs):
        self.created.append(kwargs)
        return {"acknowledged": True}

    def get_mapping(self, **kwargs):
        return self.mapping

    def put_mapping(self, **kwargs):
        self.put_mappings.append(kwargs)
        return {"acknowledged": True}

    def refresh(self, **kwargs):
        self.refreshes.append(kwargs)
        return {"_shards": {"failed": 0}}


class FakeClient:
    def __init__(self, name="fake", search_responses=None):
        self.name = name
        self.indices = FakeIndices()
        self.calls = []
        self.search_responses = list(search_responses or [])

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        if self.search_responses:
            return self.search_responses.pop(0)
        index = str(kwargs["index"]).split(",")[0]
        return {
            "_shards": {"total": 1, "successful": 1, "failed": 0},
            "hits": {"total": {"value": 1}, "hits": [{
                "_index": index, "_id": index, "_score": 1.0,
                "_source": {"route": self.name},
            }]},
        }

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return {"result": "updated"}

    def msearch(self, *, searches, max_concurrent_searches):
        self.calls.append(("msearch", {"searches": searches, "max_concurrent_searches": max_concurrent_searches}))
        responses = []
        for header, body in zip(searches[::2], searches[1::2]):
            try:
                responses.append(self.search(index=header["index"], **body))
            except Exception as exc:
                responses.append({"error": {"type": type(exc).__name__, "reason": str(exc)}})
        return {"responses": responses}

    def index(self, **kwargs):
        self.calls.append(("index", kwargs))
        return {"result": "created"}

    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return {"result": "deleted"}

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"found": True, "_id": kwargs["id"], "_source": {"title": "ok"}}

    def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        return {"count": 1, "_shards": {"failed": 0}}

    def update_by_query(self, **kwargs):
        self.calls.append(("update_by_query", kwargs))
        return {"updated": 1, "total": 1, "version_conflicts": 0, "failures": []}


@pytest.fixture
def routed_clients():
    clients = {}

    def factory(config):
        name = config["hosts"][0]
        clients[name] = clients.get(name) or FakeClient(name)
        return clients[name]

    router = IndexClientRouter(
        config={
            "default_provider": "serverless",
            "providers": {
                "serverless": {"hosts": ["serverless"]},
                "paas": {"hosts": ["paas"]},
            },
            "index_routes": {"qa_*": "serverless", "archive_*": "paas"},
        },
        client_factory=factory,
    )
    engine = EsSearchInterfaceES8(
        router=router,
        index_name="qa_default",
        vector_fields={"indexes_embedding": 3},
        ensure_index=False,
    )
    return engine, clients


def test_router_exact_and_pattern_route_and_reuses_provider(routed_clients):
    engine, clients = routed_clients
    assert engine.get_client_by_index("qa_one") is engine.get_client_by_index("qa_two")
    assert engine.get_client_by_index("archive_one") is not engine.get_client_by_index("qa_one")
    assert set(clients) == {"serverless", "paas"}


def test_mapping_and_native_nested_knn_request(routed_clients):
    engine, clients = routed_clients
    mapping = engine._build_mapping()
    for field in ("title_embedding", "content_embedding"):
        assert mapping["properties"][field]["index"] is True
        assert mapping["properties"][field]["index_options"]["type"] == "hnsw"
    nested = mapping["properties"]["indexes"]["properties"]["embedding"]
    assert nested["similarity"] == "cosine"
    engine.search_by_vector([0.1, 0.2, 0.3], "indexes_embedding", size=2)
    call = clients["serverless"].calls[-1][1]
    assert "body" not in call
    dumped = json.dumps(call["query"])
    assert "script_score" not in dumped
    assert call["query"]["bool"]["should"][0]["nested"]["query"]["knn"]["field"] == "indexes.embedding"


def test_dual_budget_and_cross_provider_index_are_preserved(routed_clients):
    engine, clients = routed_clients
    docs, total = engine.search_multi(
        {"query": "hello", "vector": {"value": [0.1, 0.2, 0.3]}},
        index_names=["qa_one", "archive_one"], size=10,
    )
    assert [doc["_index"] for doc in docs] == ["qa_one", "archive_one"]
    assert total == 2
    for client in clients.values():
        batches = [kwargs for name, kwargs in client.calls if name == "msearch"]
        assert len(batches) == 1
        assert batches[0]["max_concurrent_searches"] == 2
        calls = [kwargs for name, kwargs in client.calls if name == "search"]
        assert len(calls) == 2
        assert [c["size"] for c in calls] == [5, 5]
        assert all("body" not in c for c in calls)
        vector_call = calls[1]
        nested = vector_call["query"]["bool"]["should"][0]["nested"]
        assert nested["inner_hits"]["name"] == "best_index"
        assert "inner_hits" not in nested["query"]["knn"]


def test_same_provider_indexes_each_get_the_route_budget(routed_clients):
    engine, clients = routed_clients
    engine.search_multi(
        {"query": "hello", "vector": {"value": [0.1, 0.2, 0.3]}},
        index_names=["qa_one", "qa_two"], size=10,
    )
    calls = [kwargs for name, kwargs in clients["serverless"].calls if name == "search"]
    batches = [kwargs for name, kwargs in clients["serverless"].calls if name == "msearch"]
    assert len(batches) == 1 and len(batches[0]["searches"]) == 8
    assert [call["index"] for call in calls] == ["qa_one", "qa_one", "qa_two", "qa_two"]
    assert [call["size"] for call in calls] == [5, 5, 5, 5]


def test_crud_uses_es8_named_parameters_and_nested_update_script(routed_clients):
    engine, clients = routed_clients
    client = clients.setdefault("serverless", engine.get_client_by_index("qa_one"))
    doc = {"_id": "d1", "title": "hello", "indexes": [{"text": "hello", "embedding": [1, 0, 0]}]}
    assert engine.insert(doc, index_names="qa_one")
    assert engine.update("d1", {"ext_info.from_file_name": "a.txt"}, index_names="qa_one")
    assert engine.update_value("archive_one", {"ext_info.from_file_name": "b.txt"}, [{"_id": "d1"}])
    native = [kwargs for name, kwargs in clients["paas"].calls if name == "update_by_query"][-1]
    by_name = {name: kwargs for name, kwargs in client.calls if name in {"update", "update_by_query"}}
    assert "body" not in by_name["update"]
    assert "doc" in by_name["update"]
    assert "body" not in native and "query" in native
    assert "ctx._source['ext_info']['from_file_name']" in native["script"]["source"]


def test_page_search_is_bm25_only_and_empty_query_has_no_min_score(routed_clients):
    engine, clients = routed_clients
    engine.search_multi_by_page({}, index_names="qa_one", size=4, page_num=1, score_threshold=0.5)
    call = clients["serverless"].calls[-1][1]
    assert "min_score" not in call
    assert "knn" not in json.dumps(call["query"])
    assert set(call["source_excludes"]) == {
        "indexes.embedding", "image_indexes.embedding", "title_embedding", "content_embedding"
    }
    assert engine.search_multi_by_page(
        {"vector": {"value": [0.1]}}, index_names="qa_one"
    ) == ([], 0)


def test_partial_shards_are_retried_then_fail(routed_clients, monkeypatch):
    engine, clients = routed_clients
    client = clients["serverless"]
    client.search_responses = [{"_shards": {"failed": 1}}] * 3
    monkeypatch.setattr("kdb.retrieval.engines.es8_search_interface.time.sleep", lambda *_: None)
    with pytest.raises(RuntimeError, match="分片查询失败"):
        engine.search({}, index_names="qa_one")
    assert len([c for c in client.calls if c[0] == "search"]) == 3


def test_factory_selects_es8_without_auto_detect(monkeypatch):
    import kdb.retrieval.engines.es_search_interface as legacy_module

    selected = {}

    class Stub:
        def __init__(self, **kwargs):
            selected.update(kwargs)

    monkeypatch.setattr(legacy_module, "EsSearchInterfaceES8", Stub)
    factory = legacy_module.EsSearchInterface(
        hosts=["fake"], index_name="idx", vector_fields={"indexes_embedding": 3},
        es_version="es8.17",
    )
    assert isinstance(factory._impl, Stub)
    assert factory.es_version == "es8.17"
    assert selected["index_name"] == "idx"
