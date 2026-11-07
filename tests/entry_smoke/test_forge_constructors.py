"""Original public constructor calls; external factories are replaced, not callers."""
from types import MappingProxyType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from kdb.crud import repository as repository_module
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface


@pytest.mark.parametrize("nested", [False, True])
def test_repository_first_positional_argument_is_injected_engine(nested):
    engine = SimpleNamespace(index_name="outer", _impl=SimpleNamespace(index_name="inner") if nested else None)
    repo = KnowledgeRepository(engine)
    assert repo._engine is engine
    assert repo._default_index == ("inner" if nested else "outer")
    assert KnowledgeRepository(engine, "ignored-config", "explicit")._default_index == "explicit"


def test_repository_config_factory_and_missing_argument_failure(monkeypatch):
    engine = SimpleNamespace(index_name="configured")
    factory = Mock(return_value=engine)
    monkeypatch.setattr(repository_module, "build_legacy_engine", factory)
    with pytest.raises(ValueError, match="engine 与 engine_config_path 不能同时为空"):
        KnowledgeRepository()
    factory.assert_not_called()
    repo = KnowledgeRepository(None, "engine.json", "chosen")
    factory.assert_called_once_with(config_path="engine.json", index_name="chosen")
    assert repo._engine is engine and repo._default_index == "chosen"


def test_repository_factory_failure_is_not_swallowed(monkeypatch):
    error = ValueError("invalid supplied engine configuration")
    monkeypatch.setattr(repository_module, "build_legacy_engine", Mock(side_effect=error))
    with pytest.raises(ValueError) as caught:
        KnowledgeRepository(engine_config_path="invalid.json")
    assert caught.value is error


def test_service_original_positional_injections_have_effect_in_canonical_core():
    engine = Mock(index_name="default")
    engine._impl = None
    repo = KnowledgeRepository(engine)
    embedding = Mock(text2embedding=Mock(return_value=np.array([1., 2., 3.])))
    similarity = object()
    category = Mock()
    category.map_cate_name_to_id.return_value = "category-id"
    service = KnowledgeService(repo, embedding, "chosen", "https://files/", False, True, similarity, category)
    assert service._repo is repo and service._embedding is embedding
    assert service._default_index == "chosen"
    assert service.engine is engine and service.embedding_tools is embedding
    assert service.simility_tools is similarity and service._category is category
    assert service.check_duplicate is False and service.is_need_llm is True
    assert isinstance(service._interface, SearchDataInterface)
    assert service._interface.engine is engine and service._interface.embedding_tools is embedding
    assert service._interface.check_duplicate is False and service._interface.is_need_llm is True
    assert service.map_cate_name_to_id("tenant", "Category") == "category-id"
    category.map_cate_name_to_id.assert_called_once_with("tenant", "Category")
    document = {"content": "[multimodal_prefix]a.pdf", "multimodal_contents": [{"path": "a.pdf", "fileName": "A B.pdf"}]}
    service.render_multimodal_urls(document)
    assert document["content"] == "https://files/a.pdf?filename=A%20B.pdf"
    assert service.update("doc", {"content": "changed"}, regenerate_embedding=True) is engine.update.return_value
    payload = engine.update.call_args.args[1]
    assert payload["content_embedding"] == [1., 2., 3.]
    embedding.text2embedding.assert_called_once_with("changed")


@pytest.mark.parametrize("legacy,check,llm,expected_check,expected_llm", [
    ({}, None, None, True, False),
    ({"check_duplicate": False, "is_need_llm": True}, None, None, False, True),
    ({"check_duplicate": False, "is_need_llm": True}, True, False, True, False),
])
def test_service_old_keyword_defaults_and_overrides(legacy, check, llm, expected_check, expected_llm):
    repo = KnowledgeRepository(SimpleNamespace(index_name="default", _impl=None))
    service = KnowledgeService(repository=repo, embedding_client=None, multimodal_prefix=None,
                               check_duplicate=check, is_need_llm=llm, legacy_config=legacy)
    assert service._default_index == "default" and service._embedding is None
    assert service._multimodal_prefix == service.multimodal_prefix == ""
    assert service.check_duplicate is expected_check and service.is_need_llm is expected_llm
    assert service.simility_tools is None and service._category is service
    assert service._legacy_config == legacy and service._legacy_config is not legacy
    assert service.category_update_time_interval == 36000 and service.category_service_url == ""
    assert service.all_client_category_dict == {} and service.category_update_time_dict == {}


def test_fifth_positional_mapping_and_duplicate_config_failure():
    repo = KnowledgeRepository(SimpleNamespace(index_name="default", _impl=None))
    config = MappingProxyType({"category_service_url": "https://category.example", "category_update_time_interval": 12,
                               "check_duplicate": False, "is_need_llm": True})
    service = KnowledgeService(repo, None, None, "", config)
    assert service.category_service_url == "https://category.example"
    assert service.category_update_time_interval == 12
    assert service.check_duplicate is False and service.is_need_llm is True
    with pytest.raises(TypeError, match="both positionally and by keyword"):
        KnowledgeService(repo, None, None, "", config, legacy_config={})


def test_original_missing_service_arguments_remain_type_errors():
    with pytest.raises(TypeError):
        KnowledgeService()
    with pytest.raises(TypeError):
        KnowledgeService(SimpleNamespace(_default_index="default"))


def test_instance_method_injection_is_not_redirected_to_core():
    service = KnowledgeService(KnowledgeRepository(SimpleNamespace(index_name="default", _impl=None)), None)
    replacement = Mock(return_value=True)
    service.update = replacement
    assert service.update("id", {}) is True
    replacement.assert_called_once_with("id", {})


def test_source_count_retains_original_positional_order():
    # Earlier restart input smoke incorrectly expected the legacy count interface.
    # Preserve the original forge positional order and native repository contract.
    engine = SimpleNamespace(index_name="default", _impl=None, count_by_query=Mock(return_value=7))
    service = KnowledgeService(KnowledgeRepository(engine), None)
    assert service.get_from_type_count("chosen", "2026-01-01 00:00:00", "2026-02-01 00:00:00", "document") == (True, 7, "")
    engine.count_by_query.assert_called_once_with(
        "chosen", {"bool": {"filter": [
            {"term": {"quality_level": "high"}}, {"term": {"from_type": "document"}},
            {"range": {"insert_time": {"gte": "2026-01-01 00:00:00", "lte": "2026-02-01 00:00:00"}}},
        ]}}, require_complete=True,
    )
