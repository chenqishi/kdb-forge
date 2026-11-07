"""Offline contract checks for the old SearchDataInterface surface."""

from unittest.mock import Mock

import numpy as np
import pytest

from kdb.crud.service import KnowledgeService, SearchDataInterface


class FakeEmbedding:
    def text2embedding(self, text):
        if isinstance(text, list):
            return np.ones((len(text), 1024), dtype=float)
        return np.ones(1024, dtype=float)


class FakeEngine:
    index_name = "test"

    def __init__(self):
        self.inserted = []

    def insert(self, data, index_names=None, refresh_imm=False):
        self.inserted.append(dict(data))
        return True

    def search(self, query, size=10, index_names=None):
        return []

    def search_multi(self, query, index_names=None, size=10, page_num=1):
        doc = {
            "_id": "doc-1",
            "title": "title",
            "content": "content",
            "title_embedding": np.ones(1024).tolist(),
            "content_embedding": np.ones(1024).tolist(),
            "indexes": [],
        }
        return [doc], 1

    def search_multi_by_page(self, query, index_names=None, size=10, page_num=1, score_threshold=None):
        return [{"_id": "doc-1", "score": 5.0, "content": "content"}], 1

    def update(self, data_id, data, index_names=None):
        return True

    def delete(self, data_id, index_names=None, refresh=False):
        return True

    def get(self, data_id, index_names=None):
        return None

    def update_value(self, *args, **kwargs):
        return True

    def get_unique_values(self, *args, **kwargs):
        return []


class FakeRepository:
    _default_index = "test"

    def __init__(self, engine):
        self._engine = engine

    def search_multi(self, query, index_name=None, size=10, page_num=1, recall_mode=None):
        return self._engine.search_multi(query, index_names=index_name, size=size, page_num=page_num)


def test_old_public_names_are_exposed():
    names = {
        "insert_data",
        "batch_insert_data",
        "search_data",
        "search_data_by_query",
        "search_data_by_multi_query",
        "web_search_data",
        "update_data",
        "delete_data",
        "get_data_by_id",
        "list_file_names",
        "resolve_file_name",
        "preview_delete_by_file",
        "delete_by_file",
    }
    assert names.issubset(set(dir(KnowledgeService)))
    assert names.issubset(set(dir(SearchDataInterface)))


def test_insert_search_and_web_search_keep_old_call_shapes():
    engine = FakeEngine()
    service = KnowledgeService(FakeRepository(engine), FakeEmbedding(), default_index="test")

    ok, message = service.insert_data(
        {"title": "title", "content": "content", "data_type": "qa"},
        check_duplicate=False,
        index_name="test",
    )
    assert ok is True
    assert message == ""
    assert engine.inserted[0]["_id"]
    assert engine.inserted[0]["primary_category"]["cate1_id"] == "1"

    docs, total = service.search_data_by_query("query", index_names="test")
    assert total == 1
    assert docs[0]["similarity"] > 0

    docs, total = service.search_data_by_multi_query(["query"], index_names="test")
    assert total == 1
    assert docs[0]["similarity"] > 0

    docs, total = service.web_search_data("query", index_names="test", page_size=10)
    assert total == 1
    assert docs[0]["score"] == 1.0


def test_compat_constructor_accepts_old_engine_injection():
    service = SearchDataInterface(
        search_engine=FakeEngine(),
        embedding_client=FakeEmbedding(),
    )
    assert isinstance(service, KnowledgeService)
    assert hasattr(service, "web_search_data")


@pytest.mark.parametrize("upstream_primary", [None, {
    "category_path": "Reviewed", "category_ids": ["20"],
    "cate1_name": "Reviewed", "cate1_id": "20",
}])
def test_insert_does_not_infer_mining_categories(monkeypatch, upstream_primary):
    engine = FakeEngine()
    service = KnowledgeService(FakeRepository(engine), FakeEmbedding(), default_index="test")
    chain = [{"category_id": "10", "category_name": "Amazon", "level": 1}]
    service.all_client_category_dict["payoneer_olive"] = {
        "name_map_dict": {"Amazon": chain}, "id_map_dict": {"10": chain},
    }
    load_tree = Mock()
    monkeypatch.setattr(service, "load_category_map_dict", load_tree)
    document = {
        "client": "payoneer_olive", "title": "Amazon account", "content": "Answer",
        "data_type": "qa", "keywords": ["Amazon"],
        "ext_info": {"marketplace": "Amazon", "model_platform": "Amazon", "tags": ["Amazon"]},
    }
    if upstream_primary is not None:
        document["primary_category"] = upstream_primary

    assert service.insert_data(document, check_duplicate=False, index_name="test") == (True, "")
    stored = engine.inserted[0]
    if upstream_primary is None:
        assert stored["primary_category"]["category_ids"] == ["1"]
        assert stored["category_infos"][0]["source"] == "default"
    else:
        assert stored["primary_category"] == upstream_primary
        assert not stored.get("category_infos")
    assert stored["ext_info"]["marketplace"] == "Amazon"
    assert stored["ext_info"]["model_platform"] == "Amazon"
    assert stored["ext_info"]["tags"] == ["Amazon"]
    load_tree.assert_not_called()


@pytest.mark.parametrize("tree_available", [True, False])
def test_insert_keeps_explicit_mining_categories(monkeypatch, tree_available):
    engine = FakeEngine()
    service = KnowledgeService(FakeRepository(engine), FakeEmbedding(), default_index="test")
    chain = [{"category_id": "20", "category_name": "Reviewed", "level": 1}]
    if tree_available:
        service.all_client_category_dict["payoneer_olive"] = {
            "name_map_dict": {"Reviewed": chain}, "id_map_dict": {"20": chain},
        }
    monkeypatch.setattr(service, "load_category_map_dict", Mock(return_value=None))
    document = {
        "client": "payoneer_olive", "title": "Amazon account", "content": "Answer",
        "data_type": "qa", "keywords": ["Amazon"],
        "category_infos": [{"categoryId": 20, "categoryName": "Reviewed", "source": "model_platform"}],
    }

    assert service.insert_data(document, check_duplicate=False, index_name="test") == (True, "")
    stored = engine.inserted[0]
    assert stored["category_infos"] == [{
        "category_id": "20", "category_name": "Reviewed", "source": "model_platform",
    }]
    assert stored["primary_category"]["category_ids"] == (["20"] if tree_available else ["1"])


def test_web_search_keeps_generic_category_filter(monkeypatch):
    engine = FakeEngine()
    service = KnowledgeService(FakeRepository(engine), FakeEmbedding(), default_index="test")
    chain = [{"category_id": "20", "category_name": "Reviewed", "level": 1}]
    service.all_client_category_dict["generic_client"] = {
        "name_map_dict": {"Reviewed": chain}, "id_map_dict": {"20": chain},
    }
    search = Mock(return_value=([], 0))
    monkeypatch.setattr(engine, "search_multi_by_page", search)

    assert service.web_search_data(
        "", client="generic_client", index_names="test", page_size=10,
        condition_dicts=[{"category_names": ["Reviewed"], "category_ids": ["30"]}],
    ) == ([], 0)
    search.assert_called_once_with(
        {"attribute": [{"category_ids": ["20", "30"]}]},
        index_names=["test"], size=10, page_num=1, score_threshold=None,
    )
