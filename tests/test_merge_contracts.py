"""Offline integration checks for the two branches' service contracts."""

import copy
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

import kdb.api.knowledge_routes as routes
from kdb.api.app import app
from kdb.crud.repository import KnowledgeRepository
import kdb.crud.service as service_module
from kdb.crud.service import KnowledgeService, _FallbackSimilityTools
from tests.test_legacy_service_compat import FakeEmbedding, FakeEngine


@pytest.fixture
def service():
    return KnowledgeService(KnowledgeRepository(engine=FakeEngine()), FakeEmbedding())


def test_api_writes_reach_real_service(service, monkeypatch):
    monkeypatch.setattr(routes, "_svc", service)
    engine = service.engine
    engine.es = Mock()
    engine.insert = Mock(wraps=engine.insert)
    engine.update = Mock(return_value=True)
    engine.delete = Mock(return_value=True)
    client = TestClient(app)
    response = client.post("/knowledge/insert", json={
        "es_index": "requested", "check_duplicate": False, "refresh_imm": True,
        "doc": {"_id": "doc-1", "title": "question", "synonyms_title": ["alias"],
                "content": "answer", "data_type": "qa", "keywords": ["question"], "audit_result": 2},
    })
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["document_id"] == "doc-1"
    stored = engine.inserted[0]
    assert stored["audit_result"] == 2
    assert stored["synonyms_title"] == ["alias"]
    assert [item["text"] for item in stored["indexes"]] == ["question", "alias"]
    assert all(len(item["embedding"]) == 1024 for item in stored["indexes"])
    assert engine.insert.call_args.kwargs == {"index_names": "requested", "refresh_imm": True}

    response = client.post("/knowledge/modify_direct_update", json={
        "es_index": "requested", "updates": [{"document_id": "doc-1", "new_content": "edited"}],
    })
    assert response.json()["success"] is True
    args, kwargs = engine.update.call_args
    assert args[0] == "doc-1" and args[1]["content"] == "edited"
    assert len(args[1]["content_embedding"]) == 1024
    assert kwargs["index_names"] == "requested"
    engine.es.indices.refresh.assert_called_with(index="requested")

    response = client.post("/knowledge/delete", json={
        "es_index": "requested", "document_id": "doc-1", "refresh": True,
    })
    assert response.json()["success"] is True
    engine.delete.assert_called_once_with("doc-1", index_names="requested", refresh=True)


@pytest.mark.parametrize("audit, expected", [(2, 2), (99, -1), (0, 0)])
@pytest.mark.parametrize("existing", [True, False])
def test_upsert_keeps_remote_normalization(service, audit, expected, existing):
    document = {"title": "question", "content": "answer", "data_type": "qa",
                "keywords": ["question"], "from_type": 42, "audit_result": audit}
    if existing:
        document["_id"] = "existing"
    original = copy.deepcopy(document)
    assert service.insert_data(document, check_duplicate=False) == (True, "")
    assert document == original
    stored = service.engine.inserted[0]
    assert stored["audit_result"] == expected and stored["from_type"] == "42"


def test_default_duplicate_check_uses_fallback(service, monkeypatch):
    monkeypatch.setattr(service_module, "LegacySimilityTools", None)
    document = {"title": "question", "content": "answer", "data_type": "qa", "keywords": ["question"]}
    candidate = service._prepare_document(copy.deepcopy(document))
    candidate["_id"] = "other-document"
    monkeypatch.setattr(service.engine, "search", Mock(return_value=[candidate]))
    ok, message = service.insert_data(document)
    assert not ok and message
    assert not service.engine.inserted
    assert "_id" not in document
    monkeypatch.setattr(service.engine, "update_value", Mock(side_effect=RuntimeError("soft-delete failed")))
    assert service.insert_data(document, is_update_data=True) == (True, "")
    assert len(service.engine.inserted) == 1


@pytest.mark.parametrize("index_name, expected_indexes", [
    ("test", ["test"]), (["test"], ["test"]), ("", None), ([], None),
])
def test_remote_injection_and_search_names(monkeypatch, index_name, expected_indexes):
    engine = FakeEngine()
    engine.search_multi = Mock(wraps=engine.search_multi)
    category = Mock()
    category.map_cate_name_to_id.return_value = "category-1"
    similarity = Mock()
    similarity.is_simility_knowledge.return_value = 1
    service = KnowledgeService(
        KnowledgeRepository(engine=engine), FakeEmbedding(), "test", "https://files/",
        True, False, similarity, category, legacy_config={"check_duplicate": False},
    )
    candidate = {"_id": "other", "data_type": "qa"}
    engine.search = Mock(return_value=[candidate])
    assert service.insert_data({"title": "q", "content": "a", "keywords": ["q"]})[0] is False
    similarity.is_simility_knowledge.assert_called_once()
    assert service.batch_insert([], check_duplicate=False) == []
    docs, total = service.search_text_multi(["question"], index_name=index_name)
    assert total == 1 and docs[0]["similarity"] > 0
    assert engine.search_multi.call_args.kwargs["index_names"] == expected_indexes
    engine.search_multi_by_page = Mock(return_value=([], 0))
    assert service.web_search("", client="tenant", index_name=index_name,
                              condition_dicts=[{"category_names": ["Category"]}]) == ([], 0)
    category.map_cate_name_to_id.assert_called_once_with("tenant", "Category")
    assert engine.search_multi_by_page.call_args.kwargs["index_names"] == expected_indexes
    assert engine.search_multi_by_page.call_args.args[0]["attribute"] == [{"category_ids": ["category-1"]}]


@pytest.mark.parametrize("explicit, default, test_index, expected", [
    ("explicit", "default", "test", "explicit"),
    (None, "default", "test", "default"), (None, None, "test", "test"),
    (None, None, None, None),
])
def test_from_config_keeps_index_precedence(service, monkeypatch, explicit, default, test_index, expected):
    config = {"engine_config_path": "engine.json", "embedding_config_path": "embedding.json",
              "default_index_name": default, "test_index_name": test_index}
    monkeypatch.setattr(service_module, "load_config", Mock(return_value=config))
    monkeypatch.setattr(KnowledgeService, "_load_legacy_search_cfg", Mock(return_value={"check_duplicate": False}))
    repository = Mock(return_value=service._repo)
    monkeypatch.setattr(service_module, "KnowledgeRepository", repository)
    monkeypatch.setattr(service_module, "build_embedding_client", Mock(return_value=FakeEmbedding()))
    loaded = KnowledgeService.from_config("config.json", index_name=explicit)
    repository.assert_called_once_with(engine_config_path="engine.json", default_index=expected)
    assert loaded.check_duplicate is False


@pytest.mark.parametrize("dependency", ["legacy_gen_keyword_by_title_content", "legacy_get_from_norm_type"])
def test_processing_errors_keep_insert_error_contract(service, monkeypatch, dependency):
    monkeypatch.setattr(service_module, dependency, Mock(side_effect=RuntimeError("processing failed")))
    document = {"title": "q", "content": "a", "data_type": "qa"}
    if dependency == "legacy_get_from_norm_type":
        document["keywords"] = ["q"]
    assert service.insert_data(document, check_duplicate=False)[0] is False
    assert not service.engine.inserted
    with pytest.raises(RuntimeError, match="processing failed"):
        service.insert_text(document)


def test_api_cold_import_does_not_load_crud():
    script = """
import sys
sys.modules['kdb.crud'] = None
sys.modules['elasticsearch'] = None
from fastapi.testclient import TestClient
from kdb.api.app import app
client = TestClient(app)
assert client.get('/health').json()['status'] == 'ok'
response = client.post('/knowledge/modify_direct_update', json={
    'es_index': 'offline', 'dry_run': True,
    'updates': [{'document_id': 'd', 'new_content': 'edited'}]})
assert response.json()['success'] is True
assert response.json()['updated_items'][0]['applied'] is False
assert 'kdb.legacy_bridge' not in sys.modules
import kdb
assert not hasattr(kdb, 'not_an_export')
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_fallback_llm_requirement_is_not_silently_ignored():
    first = {"data_type": "qa", "title_embedding": [1.0, 0.0], "content_embedding": [1.0, 0.0]}
    second = {"data_type": "qa", "title_embedding": [0.8, 0.6], "content_embedding": [0.8, 0.6]}
    with pytest.raises(RuntimeError):
        _FallbackSimilityTools().is_simility_knowledge(first, second, is_need_llm=True)


def test_multimodal_missing_text_matches_remote(service):
    assert service.join_multimodal_contents([{"type": "text"}]) is None
    assert service.join_multimodal_contents([{"type": "text", "content": "a"}, {"type": "text"}]) == "a\nNone"
