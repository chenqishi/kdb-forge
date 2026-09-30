"""Merged features through the real ES8 client, with only transport IO replaced."""

import copy
import hashlib
from types import MappingProxyType, SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

from elastic_transport import ApiResponseMeta, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse
from fastapi.testclient import TestClient
import numpy as np
import pytest

import kdb.api.knowledge_routes as routes
from kdb.api.app import app
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


def embed_text(text):
    return np.array([value + 1.0 for value in hashlib.sha256(text.encode()).digest()[:3]])


@pytest.fixture
def es8_stack(monkeypatch):
    state = SimpleNamespace(calls=[], documents={}, search_hits={})

    def perform_request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        parts = url.path.strip("/").split("/")
        host, index = node.host, parts[0]
        state.calls.append({"host": host, "method": method, "path": url.path,
                            "params": parse_qs(url.query), "body": copy.deepcopy(body)})
        if len(parts) == 3 and parts[1] == "_update":
            key = (host, index, parts[2])
            assert key in state.documents or body.get("doc_as_upsert")
            state.documents.setdefault(key, {}).update(copy.deepcopy(body["doc"]))
            response = {"result": "updated"}
        elif len(parts) == 3 and parts[1] == "_doc" and method == "GET":
            key = (host, index, parts[2])
            response = {"_id": parts[2], "found": key in state.documents,
                        "_source": copy.deepcopy(state.documents.get(key, {}))}
        elif len(parts) == 3 and parts[1] == "_doc" and method == "DELETE":
            del state.documents[(host, index, parts[2])]
            response = {"result": "deleted"}
        elif parts[-1] == "_refresh":
            response = {"_shards": {"successful": 1, "failed": 0}}
        elif parts[-1] == "_search":
            hits = copy.deepcopy(state.search_hits.get(host, []))
            response = {"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits}}
        else:
            raise AssertionError(f"Unexpected ES request: {method} {target}")
        return TransportApiResponse(
            ApiResponseMeta(200, "1.1", HttpHeaders({"x-elastic-product": "Elasticsearch"}), 0, node),
            response,
        )

    monkeypatch.setattr(Transport, "perform_request", perform_request)
    router = IndexClientRouter(config={
        "providers": {"serverless": {"hosts": ["http://serverless.example:9200"]},
                      "paas": {"hosts": ["http://paas.example:9200"]}},
        "default_provider": "serverless", "index_routes": {"idx_b": "paas"},
    })
    engine = RoutedLegacyEngine(router=router, index_name="idx_a",
                                vector_fields={"indexes_embedding": 3}, ensure_index=False)
    service = KnowledgeService(KnowledgeRepository(engine=engine),
                               Mock(text2embedding=Mock(side_effect=embed_text)),
                               multimodal_prefix="https://files/")
    state.service = service
    state.router = router
    yield state
    router.close()


@pytest.mark.parametrize("config", [{}, {"check_duplicate": False, "is_need_llm": True,
                                       "category_service_url": "https://category.example"}])
def test_positional_service_config_survives_merge(es8_stack, config):
    service = KnowledgeService(es8_stack.service._repo, es8_stack.service._embedding,
                               "idx_a", "https://files/", MappingProxyType(config))
    assert service.check_duplicate is config.get("check_duplicate", True)
    assert service.is_need_llm is config.get("is_need_llm", False)
    assert service.category_service_url == config.get("category_service_url", "")
    assert service._legacy_config == config
    assert not es8_stack.calls


def test_duplicate_config_is_rejected(es8_stack):
    with pytest.raises(TypeError, match="both positionally and by keyword"):
        KnowledgeService(es8_stack.service._repo, es8_stack.service._embedding,
                         "idx_a", "", {}, legacy_config={})


@pytest.mark.parametrize("index, host", [("idx_a", "serverless.example"), ("idx_b", "paas.example")])
def test_api_crud_keeps_es8_target_and_retrieval_vectors(es8_stack, monkeypatch, index, host):
    monkeypatch.setattr(routes, "_svc", es8_stack.service)
    client = TestClient(app)
    original = {"_id": "doc-1", "title": "old question", "content": "answer", "audit_result": 2,
                "keywords": ["question"], "data_type": "qa", "del_flag": 0,
                "synonyms_title": ["alias"], "indexes": [{"text": "custom", "tag": "keep"}],
                "image_indexes": [{"text": "diagram"}]}
    result = client.post("/knowledge/insert", json={"es_index": index, "doc": original,
                         "check_duplicate": False, "refresh_imm": True})
    assert result.status_code == 200 and result.json()["success"] is True
    assert result.json()["document_id"] == "doc-1"
    key = (host, index, "doc-1")
    stored = es8_stack.documents[key]
    assert stored["audit_result"] == 2
    assert {item["text"] for item in stored["indexes"]} == {"old question", "alias", "custom", "diagram"}
    assert es8_stack.calls[0]["body"]["doc_as_upsert"] is True
    assert es8_stack.calls[0]["params"] == {"refresh": ["true"]}

    result = client.post("/knowledge/modify_direct_update", json={"es_index": index, "updates": [
        {"document_id": "doc-1", "new_title": "new question", "new_content": "new answer"},
    ]})
    assert result.json()["success"] is True, result.json()
    stored = es8_stack.documents[key]
    assert stored["title"] == "new question" and stored["content"] == "new answer"
    assert stored["title_embedding"] == embed_text("new question").tolist()
    assert stored["content_embedding"] == embed_text("new answer").tolist()
    indexes = {item["text"]: item for item in stored["indexes"]}
    assert set(indexes) == {"new question", "alias", "custom", "diagram"}
    assert indexes["new question"]["embedding"] == embed_text("new question").tolist()
    assert indexes["custom"]["tag"] == "keep"
    assert stored["synonyms_title"] == ["alias"] and stored["audit_result"] == 2
    assert es8_stack.calls[-1]["path"] == f"/{index}/_refresh"

    result = client.post("/knowledge/delete", json={"es_index": index, "document_id": "doc-1", "refresh": True})
    assert result.json()["success"] is True
    assert key not in es8_stack.documents
    assert {call["host"] for call in es8_stack.calls} == {host}
    assert all(call["path"].startswith(f"/{index}/") for call in es8_stack.calls)
    delete = next(call for call in es8_stack.calls if call["method"] == "DELETE")
    assert delete["params"] == {"refresh": ["true"]}


@pytest.mark.parametrize("patch, regenerate, expected", [
    ({"title": "new"}, True, {"old", "new", "alias", "custom", "diagram"}),
    ({"title": "", "synonyms_title": [], "content": ""}, True, {"custom", "diagram"}),
    ({"synonyms_title": ["new alias"]}, True, {"old", "new alias", "custom", "diagram"}),
    ({"title": "new", "indexes": [{"text": "explicit"}]}, True, {"explicit"}),
    ({"title": "new"}, False, {"old", "alias", "custom", "diagram"}),
])
def test_update_preserves_unrelated_indexes(es8_stack, patch, regenerate, expected):
    key = ("paas.example", "idx_b", "doc-1")
    es8_stack.documents[key] = {
        "title": "old", "synonyms_title": ["old", "alias"], "content": "answer",
        "title_embedding": embed_text("old").tolist(),
        "content_embedding": embed_text("answer").tolist(),
        "indexes": [{"text": text, "embedding": embed_text(text).tolist()}
                    for text in ["old", "alias", "custom", "diagram"]],
        "image_indexes": [{"text": "diagram"}],
    }
    original = copy.deepcopy(patch)
    assert es8_stack.service.update("doc-1", patch, index_name="idx_b", regenerate_embedding=regenerate)
    assert patch == original
    stored = es8_stack.documents[key]
    assert {item["text"] for item in stored["indexes"]} == expected
    if patch.get("title") == "":
        assert stored["title_embedding"] is None and stored["content_embedding"] is None
    if "indexes" in patch or not regenerate:
        assert len(es8_stack.calls) == 1  # An explicit index patch needs no read/merge.


def test_title_update_without_stored_document_does_not_write(es8_stack):
    with pytest.raises(ValueError, match="stored document"):
        es8_stack.service.update("missing", {"title": "new"}, index_name="idx_b", regenerate_embedding=True)
    assert [call["method"] for call in es8_stack.calls] == ["GET"]


@pytest.mark.parametrize("method, query", [("search_text", "question"), ("search_text_multi", ["question"])])
def test_dual_native_retrieval_routes_and_deduplicates(es8_stack, method, query):
    for index, host in [("idx_a", "serverless.example"), ("idx_b", "paas.example")]:
        es8_stack.search_hits[host] = [{"_index": index, "_id": "same-id", "_score": 2.0, "_source": {
            "title": "question", "title_embedding": embed_text("question").tolist(),
            "content": "[multimodal_prefix]report.pdf", "audit_result": 2,
            "multimodal_contents": [{"type": "file", "path": "report.pdf", "fileName": "a b.pdf"}],
        }}]
    docs, total = getattr(es8_stack.service, method)(query, index_name=["idx_a", "idx_b"], size=4)
    assert len(docs) == 2 and total == 2  # Dedup within a route, not across distinct indexes.
    assert all(doc["similarity"] > 0 and doc["content"] == "https://files/report.pdf?filename=a%20b.pdf"
               for doc in docs)
    assert len(es8_stack.calls) == 4
    for offset, host in [(0, "serverless.example"), (2, "paas.example")]:
        bm25, vector = es8_stack.calls[offset:offset + 2]
        assert bm25["host"] == vector["host"] == host
        assert "knn" not in str(bm25["body"])
        assert "match" in str(bm25["body"])
        knn = vector["body"]["query"]["bool"]["should"][0]["nested"]["query"]["knn"]
        assert knn["field"] == "indexes.embedding"
        assert knn["query_vector"] == embed_text("question").tolist()
        assert knn["filter"] == bm25["body"]["query"]["bool"]["must"][0]
        assert "del_flag" in str(knn["filter"])
        assert "script_score" not in str(vector["body"])


def test_web_pagination_stays_bm25_on_requested_provider(es8_stack):
    category = Mock()
    category.map_cate_name_to_id.return_value = "category-1"
    es8_stack.service._category = category
    assert es8_stack.service.web_search("question", client="tenant", index_name="idx_b",
        condition_dicts=[{"category_names": ["Category"]}], page_num=2, page_size=3,
        score_threshold=0.2) == ([], 0)
    category.map_cate_name_to_id.assert_called_once_with("tenant", "Category")
    assert len(es8_stack.calls) == 1
    call = es8_stack.calls[0]
    assert call["host"] == "paas.example" and call["path"] == "/idx_b/_search"
    assert call["body"]["from"] == 3 and call["body"]["size"] == 3
    assert call["body"]["min_score"] == 0.2
    assert "category-1" in str(call["body"]) and "knn" not in str(call["body"])


@pytest.mark.parametrize("version", ["7.10", "7.17.13", "9.0"])
def test_non_es8_configuration_is_rejected(es8_stack, version):
    with pytest.raises(ValueError, match="8.17"):
        RoutedLegacyEngine(config={"es_version": version}, router=es8_stack.router,
                           index_name="idx_a", vector_fields={"indexes_embedding": 3}, ensure_index=False)
    assert not es8_stack.calls
