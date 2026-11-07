"""Public repository protocol examples: argument order, defaults and return values."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from kdb.crud.repository import KnowledgeRepository


@pytest.mark.parametrize("method,args,kwargs,backend,expected_args,expected_kwargs,result", [
    ("count_by_query", ("chosen", {"term": {"flag": 1}}), {}, "count_by_query",
     ("chosen", {"term": {"flag": 1}}), {"require_complete": True}, 17),
    ("ensure_index", ("chosen",), {}, "_ensure_index", ("chosen",), {}, None),
    ("insert", ({"_id": "id"}, "chosen", True), {}, "insert", ({"_id": "id"},),
     {"index_names": "chosen", "refresh_imm": True}, True),
    ("update_by_id", ("id", {"content": "changed"}, "chosen"), {}, "update",
     ("id", {"content": "changed"}), {"index_names": "chosen"}, True),
    ("update_by_condition", ({"del_flag": 1}, [{"id": "id"}], "chosen"), {}, "update_value",
     ("chosen", {"del_flag": 1}, [{"id": "id"}]), {}, True),
    ("get_client_by_index", ("chosen",), {}, "get_client_by_index", ("chosen",), {}, "client"),
    ("delete", ("id", "chosen"), {}, "delete", ("id",), {"index_names": "chosen", "refresh": False}, True),
    ("get", ("id", "chosen"), {}, "get", ("id",), {"index_names": "chosen"}, {"_id": "id"}),
    ("search", ({"query": "text"}, 3, ["a", "b"]), {}, "search", ({"query": "text"}, 3),
     {"index_names": ["a", "b"]}, [{"_id": "id"}]),
    ("search_multi", ({"query": "text"}, ["a", "b"], 3, 2, "legacy"), {}, "search_multi",
     ({"query": "text"},), {"index_names": ["a", "b"], "size": 3, "page_num": 2, "recall_mode": "legacy"}, ([], 0)),
    ("search_by_page", ({"query": "text"}, "chosen", 3, 2, .2), {}, "search_multi_by_page",
     ({"query": "text"},), {"index_names": "chosen", "size": 3, "page_num": 2, "score_threshold": .2}, ([], 0)),
    ("get_unique_values", ("source", "chosen", 8, True, {"term": {"flag": 1}}), {}, "get_unique_values",
     ("chosen", "source", 8, True, {"term": {"flag": 1}}), {}, [{"key": "one", "doc_count": 1}]),
])
def test_original_public_calls(method, args, kwargs, backend, expected_args, expected_kwargs, result):
    engine = Mock(index_name="default")
    engine._impl = None
    target = getattr(engine, backend)
    target.return_value = result
    actual = getattr(KnowledgeRepository(engine), method)(*args, **kwargs)
    assert actual is result
    target.assert_called_once_with(*expected_args, **expected_kwargs)


def test_count_never_replaces_explicit_index_or_invents_query():
    engine = Mock(index_name="default")
    engine._impl = None
    query = {"bool": {"must_not": [{"term": {"del_flag": 1}}]}}
    repo = KnowledgeRepository(engine)
    repo.count_by_query("", query)
    engine.count_by_query.assert_called_once_with("", query, require_complete=True)


def test_index_default_only_applies_to_none_and_recall_mode_none_is_omitted():
    engine = Mock(index_name="default")
    engine._impl = None
    repo = KnowledgeRepository(engine)
    repo.get("id")
    engine.get.assert_called_once_with("id", index_names="default")
    repo.get("id", index_name="")
    assert engine.get.call_args.kwargs["index_names"] == ""
    repo.search_multi({"query": "text"})
    engine.search_multi.assert_called_once_with({"query": "text"}, index_names="default", size=10, page_num=1)


def test_non_routed_ensure_and_client_fallback_use_existing_impl():
    implementation = SimpleNamespace(index_name="old", _ensure_index=Mock(), es=object())
    engine = SimpleNamespace(_impl=implementation)
    repo = KnowledgeRepository(engine)
    assert repo.ensure_index() is None
    implementation._ensure_index.assert_called_once_with("old")
    assert repo.get_client_by_index("old") is implementation.es


@pytest.mark.parametrize("method,args", [
    ("update_by_condition", ({"del_flag": 1}, [{"id": "id"}])),
    ("delete", ("id",)),
])
def test_refresh_tracks_success_for_existing_write_contract(method, args):
    engine = Mock(index_name="default")
    engine._impl = None
    backend = engine.update_value if method == "update_by_condition" else engine.delete
    backend.return_value = False
    repo = KnowledgeRepository(engine)
    assert getattr(repo, method)(*args, index_name="chosen", refresh=True) is False
    engine.get_client_by_index.assert_not_called()
    backend.return_value = True
    assert getattr(repo, method)(*args, index_name="chosen", refresh=True) is True
    engine.get_client_by_index.return_value.indices.refresh.assert_called_once_with(index="chosen")
