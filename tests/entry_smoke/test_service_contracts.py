"""Current public service and lifecycle contracts under replaced I/O boundaries."""
import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import Mock


def test_public_application_export_keeps_category_behavior():
    package = importlib.import_module("kdb")
    canonical = importlib.import_module("kdb.retrieval.application.search_index_data_interface")
    assert package.SearchDataInterface is canonical.SearchDataInterface
    assert hasattr(canonical.SearchDataInterface, "infer_payoneer_olive_category")


def test_retrieval_keeps_all_twelve_post_routes():
    service = importlib.import_module("kdb.services.retrieval.app")
    expected = {
        "/search", "/web_search", "/get_from_type_count", "/insert", "/delete",
        "/get_value_collection", "/list_file_names", "/preview_delete_by_file",
        "/delete_by_file", "/update_by_condition", "/modify_knowledge_direct_update",
        "/modify_knowledge",
    }
    actual = {route.path for route in service.app.routes if "POST" in getattr(route, "methods", ())}
    assert actual == expected


def test_service_lifespan_constructs_both_real_factory_roles(monkeypatch):
    module = importlib.import_module("kdb.services.retrieval.app")
    interface = SimpleNamespace(engine=Mock())
    modifier = object()
    initialize = Mock(return_value=interface)
    modify_factory = Mock(return_value=modifier)
    monkeypatch.setattr(module, "SEARCH_DATA_INTERFACE", None)
    monkeypatch.setattr(module, "MODIFY_KNOWLEDGE_HANDLE", None)
    monkeypatch.setattr(module, "init_config", initialize)
    monkeypatch.setattr(module, "ModifyKnowledge", modify_factory)
    monkeypatch.setattr(module.sys, "argv", ["kdb.services.retrieval.app", "isolated-test-config.json"])

    async def run():
        async with module.lifespan(module.app):
            assert module.SEARCH_DATA_INTERFACE is interface
            assert module.MODIFY_KNOWLEDGE_HANDLE is modifier

    asyncio.run(run())
    initialize.assert_called_once_with("isolated-test-config.json")
    modify_factory.assert_called_once_with(interface)
