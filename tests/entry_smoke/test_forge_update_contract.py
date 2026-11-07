"""Retained forge update protocol through the single engine, with transport IO replaced."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

from elastic_transport import ApiResponseMeta, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse
from fastapi.testclient import TestClient
import pytest

import kdb.api.knowledge_routes as routes
from kdb.api.app import app
from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.services.forge_compat.adapter import KnowledgeService
# Reuse unchanged assertions by file path. The two historical test trees both
# contain a package named tests; neither package name is a stable import root.
_baseline_path = Path(__file__).resolve().parents[1] / "baseline_forge/tests/test_es8_merge_regressions.py"
_spec = importlib.util.spec_from_file_location("_forge_update_baseline", _baseline_path)
_baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_baseline)
embed_text = _baseline.embed_text
test_update_preserves_unrelated_indexes = _baseline.test_update_preserves_unrelated_indexes
test_title_update_without_stored_document_does_not_write = _baseline.test_title_update_without_stored_document_does_not_write
test_positional_service_config_survives_merge = _baseline.test_positional_service_config_survives_merge
test_duplicate_config_is_rejected = _baseline.test_duplicate_config_is_rejected


@pytest.fixture
def es8_stack(monkeypatch):
    state = SimpleNamespace(calls=[], documents={}, fail_refresh=False)

    def perform_request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        parts = url.path.strip("/").split("/")
        host, index = node.host, parts[0]
        state.calls.append({"host": host, "method": method, "path": url.path,
                            "params": parse_qs(url.query), "body": copy.deepcopy(body)})
        if len(parts) == 3 and parts[1] == "_update":
            if parts[2] == "write-error":
                raise RuntimeError("injected transport write failure")
            key = (host, index, parts[2])
            assert key in state.documents
            state.documents[key].update(copy.deepcopy(body["doc"]))
            response = {"result": "updated"}
        elif len(parts) == 3 and parts[1] == "_doc" and method == "GET":
            key = (host, index, parts[2])
            response = {"_id": parts[2], "found": key in state.documents,
                        "_source": copy.deepcopy(state.documents.get(key, {}))}
        elif parts[-1] == "_refresh":
            if state.fail_refresh:
                raise RuntimeError("injected refresh failure")
            response = {"_shards": {"successful": 1, "failed": 0}}
        else:
            raise AssertionError(f"Unexpected request: {method} {target}")
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
    engine = EsSearchInterfaceES8(router=router, index_name="idx_a",
                                vector_fields={"indexes_embedding": 3}, ensure_index=False)
    state.embedding = Mock(text2embedding=Mock(side_effect=embed_text))
    state.interface = SimpleNamespace(engine=engine, embedding_tools=state.embedding,
                                     map_cate_name_to_id=Mock(return_value=None))
    state.service = KnowledgeService._from_interface(state.interface, "idx_a")
    yield state
    router.close()


def seed(state, document_id="doc-1", index="idx_b", host="paas.example"):
    value = {"title": "old", "content": "answer", "synonyms_title": ["alias"],
             "audit_result": 2, "indexes": [{"text": text, "embedding": embed_text(text).tolist()}
                                            for text in ("old", "alias", "custom", "diagram")],
             "image_indexes": [{"text": "diagram"}]}
    state.documents[(host, index, document_id)] = value
    return value


@pytest.mark.parametrize("index,host", [("idx_a", "serverless.example"), ("idx_b", "paas.example")])
def test_real_update_route_rebuilds_vectors_and_retains_other_fields(es8_stack, monkeypatch, index, host):
    stored = seed(es8_stack, index=index, host=host)
    monkeypatch.setattr(routes, "_svc", es8_stack.service)
    result = TestClient(app).post("/knowledge/modify_direct_update", json={
        "es_index": index, "updates": [{"document_id": "doc-1", "new_title": "new", "new_content": "new answer"}],
    })
    assert result.status_code == 200 and result.json()["success"] is True
    assert result.json()["errors"] == [] and result.json()["updated_items"][0]["applied"] is True
    assert stored["title_embedding"] == embed_text("new").tolist()
    assert stored["content_embedding"] == embed_text("new answer").tolist()
    assert {item["text"] for item in stored["indexes"]} == {"new", "alias", "custom", "diagram"}
    assert all(item["embedding"] == embed_text(item["text"]).tolist() for item in stored["indexes"])
    assert stored["audit_result"] == 2 and stored["image_indexes"] == [{"text": "diagram"}]
    assert "update_time" in stored
    assert {call["host"] for call in es8_stack.calls} == {host}
    assert es8_stack.calls[-1]["path"] == f"/{index}/_refresh"


def test_update_without_regeneration_keeps_caller_fields_and_does_not_fetch(es8_stack):
    stored = seed(es8_stack)
    patch = {"_id": "discard", "title": "new"}
    assert es8_stack.service.update(data_id="doc-1", doc=patch, index_name="idx_b")
    assert patch == {"_id": "discard", "title": "new"}
    assert stored["title"] == "new" and "_id" not in stored and "update_time" in stored
    assert [call["method"] for call in es8_stack.calls] == ["POST"]
    es8_stack.embedding.text2embedding.assert_not_called()


def test_content_only_regenerates_without_fetching_stored_document(es8_stack):
    stored = seed(es8_stack)
    previous_indexes = copy.deepcopy(stored["indexes"])
    assert es8_stack.service.update("doc-1", {"content": "changed"}, index_name="idx_b", regenerate_embedding=True)
    assert stored["content_embedding"] == embed_text("changed").tolist()
    assert stored["indexes"] == previous_indexes
    assert len(es8_stack.calls) == 1


def test_refresh_failure_keeps_successful_update_result(es8_stack):
    seed(es8_stack)
    es8_stack.fail_refresh = True
    assert es8_stack.service.update("doc-1", {"content": "changed"}, index_name="idx_b", refresh=True)
    assert es8_stack.calls[-1]["path"] == "/idx_b/_refresh"


def test_failed_update_does_not_refresh(es8_stack, monkeypatch):
    update = Mock(return_value=False)
    monkeypatch.setattr(es8_stack.interface.engine, "update", update)
    assert es8_stack.service.update("doc-1", {"content": "changed"}, refresh=True) is False
    assert es8_stack.calls == []


def test_embedding_failure_propagates_before_write(es8_stack):
    es8_stack.embedding.text2embedding.side_effect = ValueError("embedding unavailable")
    with pytest.raises(ValueError, match="embedding unavailable"):
        es8_stack.service.update("doc-1", {"content": "changed"}, regenerate_embedding=True)
    assert es8_stack.calls == []


def test_route_preserves_partial_success_and_attempts_optional_insert(es8_stack, monkeypatch):
    stored = seed(es8_stack, document_id="ok")
    # Insert is outside this update correction; capture its existing interface boundary.
    es8_stack.interface.insert_data = Mock(return_value=(True, ""))
    monkeypatch.setattr(routes, "_svc", es8_stack.service)
    body = TestClient(app).post("/knowledge/modify_direct_update", json={
        "es_index": "idx_b", "updates": [
            {"document_id": "ok", "new_title": "new", "new_content": "changed"},
            {"document_id": "missing", "new_title": "new", "new_content": "changed"},
            {"document_id": "write-error", "new_content": "changed"},
        ], "allow_insert": True, "insert": {"title": "optional", "content": "answer"},
    }).json()
    assert body["success"] is False and body["has_correction"] is True
    assert [item["applied"] for item in body["updated_items"]] == [True, False, False]
    assert len(body["errors"]) == 2 and body["inserted_item"]["applied"] is True
    assert stored["content_embedding"] == embed_text("changed").tolist()
    es8_stack.interface.insert_data.assert_called_once()
    assert es8_stack.interface.insert_data.call_args.kwargs["index_name"] == "idx_b"


def test_dry_run_does_not_fetch_embed_or_write(es8_stack, monkeypatch):
    monkeypatch.setattr(routes, "_svc", es8_stack.service)
    body = TestClient(app).post("/knowledge/modify_direct_update", json={
        "es_index": "idx_b", "dry_run": True,
        "updates": [{"document_id": "doc-1", "new_title": "new", "new_content": "changed"}],
    }).json()
    assert body["success"] is True and body["updated_items"][0]["applied"] is False
    assert es8_stack.calls == []
    es8_stack.embedding.text2embedding.assert_not_called()
