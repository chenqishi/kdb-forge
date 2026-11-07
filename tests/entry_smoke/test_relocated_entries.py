"""Small checks for the mechanical wrappers, not an external-system harness."""
import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import Mock


def test_legacy_and_canonical_application_share_one_class():
    legacy = importlib.import_module("knowledge_interface_tools.search_index_data_interface")
    canonical = importlib.import_module("kdb.retrieval.application.search_index_data_interface")
    assert legacy is canonical
    assert legacy.SearchDataInterface is canonical.SearchDataInterface
    assert hasattr(canonical.SearchDataInterface, "infer_payoneer_olive_category")


def test_legacy_retrieval_wrapper_keeps_all_twelve_post_routes(monkeypatch):
    legacy = importlib.import_module("knowledge_database_search_service.src.knowledge_database_search_es")
    canonical = importlib.import_module("kdb.services.retrieval.app")
    assert legacy is canonical
    expected = {
        "/search", "/web_search", "/get_from_type_count", "/insert", "/delete",
        "/get_value_collection", "/list_file_names", "/preview_delete_by_file",
        "/delete_by_file", "/update_by_condition", "/modify_knowledge_direct_update",
        "/modify_knowledge",
    }
    actual = {route.path for route in canonical.app.routes if "POST" in getattr(route, "methods", ())}
    assert actual == expected
    sentinel = object()
    monkeypatch.setattr(legacy, "SEARCH_DATA_INTERFACE", sentinel)
    assert canonical.SEARCH_DATA_INTERFACE is sentinel


def test_original_lifespan_constructs_both_real_factory_roles(monkeypatch):
    module = importlib.import_module("kdb.services.retrieval.app")
    interface = SimpleNamespace(engine=Mock())
    modifier = object()
    initialize = Mock(return_value=interface)
    modify_factory = Mock(return_value=modifier)
    monkeypatch.setattr(module, "SEARCH_DATA_INTERFACE", None)
    monkeypatch.setattr(module, "MODIFY_KNOWLEDGE_HANDLE", None)
    monkeypatch.setattr(module, "init_config", initialize)
    monkeypatch.setattr(module, "ModifyKnowledge", modify_factory)
    monkeypatch.setattr(module.sys, "argv", ["legacy.py", "isolated-test-config.json"])

    async def run():
        async with module.lifespan(module.app):
            assert module.SEARCH_DATA_INTERFACE is interface
            assert module.MODIFY_KNOWLEDGE_HANDLE is modifier

    asyncio.run(run())
    initialize.assert_called_once_with("isolated-test-config.json")
    modify_factory.assert_called_once_with(interface)


def test_forge_plain_update_preserves_default_without_embedding():
    from kdb.services.forge_compat.adapter import KnowledgeService
    interface = Mock()
    interface.engine.update.return_value = True
    service = KnowledgeService._from_interface(interface, "test_index")
    original = {"_id": "ignored", "title": "new"}
    assert service.update(data_id="id", doc=original)
    args, kwargs = interface.engine.update.call_args
    assert args[0] == "id" and args[1]["title"] == "new"
    assert "_id" not in args[1] and "update_time" in args[1]
    assert kwargs == {"index_names": "test_index"}
    assert original == {"_id": "ignored", "title": "new"}
    interface.embedding_tools.text2embedding.assert_not_called()
