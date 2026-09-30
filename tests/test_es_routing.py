"""ES client routing and retrieval-result compatibility tests."""

import pytest

from kdb.crud.service import KnowledgeService
from kdb.crud.repository import KnowledgeRepository
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


def test_router_maps_index_to_provider_and_reuses_client():
    config = {
        "default_provider": "serverless",
        "providers": {
            "serverless": {"hosts": ["https://serverless.example"]},
            "pass": {"hosts": ["https://paas.example"]},
        },
        "index_routes": {
            "qa_serverless": "serverless",
            "qa_paas": "paas",
            "tenant_*": "pass",
        },
    }
    created = []

    def factory(provider_config):
        client = object()
        created.append((provider_config["hosts"][0], client))
        return client

    router = IndexClientRouter(config=config, client_factory=factory)
    assert router.resolve_provider("qa_serverless") == "serverless"
    assert router.resolve_provider("qa_paas") == "paas"
    assert router.resolve_provider("tenant_001") == "paas"
    assert router.get_client_by_index("qa_serverless") is router.get_client_by_index("qa_serverless")
    assert router.get_client_by_index("qa_paas") is router.get_client_by_index("tenant_001")
    assert [host for host, _ in created] == [
        "https://serverless.example",
        "https://paas.example",
    ]


def test_routed_engine_uses_es8_named_search_and_splits_cross_provider():
    class FakeClient:
        def __init__(self, name):
            self.name = name
            self.search_calls = []
            self.indices = self

        def exists(self, **kwargs):
            return False

        def create(self, **kwargs):
            return {"acknowledged": True}

        def get_mapping(self, **kwargs):
            return {}

        def search(self, **kwargs):
            self.search_calls.append(kwargs)
            index = kwargs["index"].split(",")[0]
            return {
                "hits": {
                    "total": {"value": 1, "relation": "eq"},
                    "hits": [{"_index": index, "_id": index, "_score": 1.0, "_source": {"route": self.name}}],
                }
            }

    router = IndexClientRouter(
        config={
            "default_provider": "serverless",
            "providers": {
                "serverless": {"hosts": ["serverless"]},
                "paas": {"hosts": ["paas"]},
            },
            "index_routes": {"idx_a": "serverless", "idx_b": "paas"},
        },
        client_factory=lambda cfg: FakeClient(cfg["hosts"][0]),
    )
    engine = RoutedLegacyEngine(
        router=router,
        index_name="idx_a",
        vector_fields={"indexes_embedding": 3},
        ensure_index=False,
    )
    docs, total = engine.search_multi(
        {"query": "hello"}, index_names=["idx_a", "idx_b"], size=4
    )
    assert [doc["_id"] for doc in docs] == ["idx_a", "idx_b"]
    assert [doc["route"] for doc in docs] == ["serverless", "paas"]
    assert total == 2
    assert all("body" not in call for client in router._clients.values() for call in client.search_calls)
    assert all("query" in call for client in router._clients.values() for call in client.search_calls)
    repo = KnowledgeRepository(engine=engine, default_index="idx_a")
    repo.ensure_index("idx_b")
    assert engine._impls["idx_b"].es.name == "paas"


def test_native_knn_mapping_and_query_are_used():
    class FakeIndices:
        def exists(self, **kwargs):
            return False

        def create(self, **kwargs):
            self.created = kwargs
            return {"acknowledged": True}

        def refresh(self, **kwargs):
            return {"_shards": {"successful": 1}}

    class FakeClient:
        def __init__(self):
            self.indices = FakeIndices()
            self.calls = []

        def search(self, **kwargs):
            self.calls.append(kwargs)
            return {"hits": {"total": {"value": 1}, "hits": []}}

    clients = []

    def factory(_config):
        client = FakeClient()
        clients.append(client)
        return client

    router = IndexClientRouter(
        config={"hosts": ["es8"], "index_name": "idx", "vector_fields": {"indexes_embedding": 3}},
        client_factory=factory,
    )
    engine = RoutedLegacyEngine(
        router=router,
        index_name="idx",
        vector_fields={"indexes_embedding": 3},
        ensure_index=False,
    )
    mapping = engine._build_mapping()
    embedding = mapping["properties"]["indexes"]["properties"]["embedding"]
    assert embedding["index"] is True
    assert embedding["similarity"] == "cosine"
    assert embedding["index_options"]["type"] == "hnsw"
    for field in ("title_embedding", "content_embedding"):
        root_vector = mapping["properties"][field]
        assert root_vector["index"] is True
        assert root_vector["similarity"] == "cosine"
        assert root_vector["index_options"]["type"] == "hnsw"

    engine.search_by_vector([0.1, 0.2, 0.3], "indexes_embedding", size=2)
    call = clients[0].calls[-1]
    assert "body" not in call
    assert "query" in call
    assert "script_score" not in str(call["query"])
    assert call["query"]["bool"]["should"][0]["nested"]["query"]["knn"]["field"] == "indexes.embedding"
    engine.search_by_vector(
        [0.1, 0.2, 0.3],
        "indexes_embedding",
        size=2,
        extra_query={"attribute": {"platform": ["qa"]}},
    )
    filtered_knn = clients[0].calls[-1]["query"]["bool"]["should"][0]["nested"]["query"]["knn"]
    assert filtered_knn["filter"]["bool"]["must"][-1] == {"term": {"del_flag": 0}}


def test_es8_crud_uses_named_document_and_query_parameters():
    class FakeIndices:
        def refresh(self, **kwargs):
            return {}

    class FakeClient:
        def __init__(self):
            self.indices = FakeIndices()
            self.calls = []

        def update(self, **kwargs):
            self.calls.append(("update", kwargs))
            return {"result": "updated"}

        def delete(self, **kwargs):
            self.calls.append(("delete", kwargs))
            return {"result": "deleted"}

        def get(self, **kwargs):
            self.calls.append(("get", kwargs))
            return {"_id": kwargs["id"], "_source": {"title": "ok"}}

        def index(self, **kwargs):
            self.calls.append(("index", kwargs))
            return {"result": "created"}

        def update_by_query(self, **kwargs):
            self.calls.append(("update_by_query", kwargs))
            return {"updated": 1, "failures": []}

    client = FakeClient()
    router = IndexClientRouter(
        config={"hosts": ["es8"]},
        client_factory=lambda _config: client,
    )
    engine = RoutedLegacyEngine(router=router, index_name="idx", vector_fields={"indexes_embedding": 3}, ensure_index=False)
    doc = {"_id": "doc-1", "title": "title", "indexes": [{"text": "title", "embedding": [1, 0, 0]}]}
    assert engine.insert(doc, index_names="idx", refresh_imm=True)
    assert engine.update("doc-1", {"title": "new"}, index_names="idx")
    assert engine.get("doc-1", index_names="idx")["title"] == "ok"
    assert engine.delete("doc-1", index_names="idx", refresh=True)
    assert engine.update_value("idx", {"del_flag": 1}, [{"title": "title"}])
    assert engine.insert_with_vectors({"_id": "doc-2"}, {"title_embedding": [1, 0, 0]}, index_name="idx")

    by_name = {name: kwargs for name, kwargs in client.calls if name in {"update", "delete", "get", "index", "update_by_query"}}
    assert "body" not in by_name["update"]
    assert "doc" in by_name["update"]
    assert "body" not in by_name["update_by_query"]
    assert "query" in by_name["update_by_query"]
    assert "script" in by_name["update_by_query"]
    assert "document" in by_name["index"]


def test_legacy_unindexed_vector_mapping_requires_reindex():
    class FakeIndices:
        def exists(self, **kwargs):
            return True

        def get_mapping(self, **kwargs):
            return {
                "idx": {
                    "mappings": {
                        "properties": {
                            "indexes": {
                                "type": "nested",
                                "properties": {"embedding": {"type": "dense_vector", "dims": 3}},
                            }
                        }
                    }
                }
            }

    class FakeClient:
        def __init__(self):
            self.indices = FakeIndices()

    router = IndexClientRouter(config={"hosts": ["es8"]}, client_factory=lambda _config: FakeClient())
    with pytest.raises(RuntimeError, match="native KNN mapping"):
        RoutedLegacyEngine(router=router, index_name="idx", vector_fields={"indexes_embedding": 3})


def test_service_multimodal_render_matches_legacy_filename_rule():
    class FakeRepository:
        _default_index = "test"

    service = KnowledgeService(
        repository=FakeRepository(),
        embedding_client=object(),
        multimodal_prefix="https://file.example/",
    )
    doc = {
        "content": "[multimodal_prefix]/files/report.xlsx",
        "multimodal_contents": [
            {"type": "file", "path": "/files/report.xlsx", "fileName": "报告 1.xlsx"}
        ],
    }
    service.render_multimodal_urls(doc)
    assert doc["content"] == (
        "https://file.example//files/report.xlsx?filename="
        "%E6%8A%A5%E5%91%8A%201.xlsx"
    )
