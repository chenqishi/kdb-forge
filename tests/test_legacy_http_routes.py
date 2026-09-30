"""Offline contract tests for the remaining old :8003 HTTP routes.

All service and modifier calls are fake; this module never opens an ES connection.
"""

import pytest
from fastapi.testclient import TestClient

from kdb.api.app import app
from kdb.api import legacy_routes as lr


class FakeService:
    def __init__(self):
        self.calls = []

    def insert_data(self, doc, **kwargs):
        self.calls.append(("insert_data", doc, kwargs))
        return True, ""

    def delete_data(self, *args, **kwargs):
        self.calls.append(("delete_data", args, kwargs))
        return True

    def get_unique_values(self, **kwargs):
        self.calls.append(("get_unique_values", kwargs))
        return [{"value": "x", "doc_count": 2}] if kwargs["include_doc_count"] else ["x"]

    def list_file_names(self, **kwargs):
        self.calls.append(("list_file_names", kwargs))
        return [{"value": "a.pdf", "doc_count": 1, "type_count": {"document": 1}}]

    def preview_delete_by_file(self, **kwargs):
        self.calls.append(("preview_delete_by_file", kwargs))
        return {"total_count": 1, "by_file": [], "type_count": {}, "samples": [], "warnings": []}

    def delete_by_file(self, **kwargs):
        self.calls.append(("delete_by_file", kwargs))
        return {"success": True, "deleted_count": 1, "snapshot_path": "tmp/s.jsonl", "message": "ok"}

    def update_data_value(self, **kwargs):
        self.calls.append(("update_data_value", kwargs))
        return True


class FakeModifier:
    def __init__(self):
        self.calls = []

    def modify_knowledge_direct_update(self, **kwargs):
        self.calls.append(("direct", kwargs))
        return "updated", True

    def modify_knowledge(self, **kwargs):
        self.calls.append(("modify", kwargs))
        return [{"_id": "d1", "content": "new"}]


@pytest.fixture()
def client():
    lr._service = FakeService()
    lr._modifier = None
    yield TestClient(app)
    lr._service = None
    lr._modifier = None


def test_all_legacy_routes_are_mounted():
    paths = set(app.openapi()["paths"])
    assert {
        "/search", "/insert", "/delete", "/web_search", "/get_value_collection",
        "/list_file_names", "/preview_delete_by_file", "/delete_by_file",
        "/update_by_condition", "/modify_knowledge_direct_update", "/modify_knowledge",
    }.issubset(paths)


def test_insert_preserves_old_fields_and_category_conversion(client):
    r = client.post("/insert", json={
        "_id": "d1", "title": "Q", "content": "A", "index_names": "idx",
        "categoryId": "10,20", "categoryName": "Root,Leaf", "custom": "kept",
        "refresh_imm": True, "is_update_data": False,
    })
    assert r.status_code == 200
    assert r.json() == {"success": True, "message": "数据已插入: Q"}
    call = lr._service.calls[0]
    assert call[0] == "insert_data"
    assert call[1]["_id"] == "d1"
    assert call[1]["category_infos"][1]["category_id"] == "20"
    assert call[1]["custom"] == "kept"
    assert call[2]["index_name"] == "idx"
    assert call[2]["refresh_imm"] is True
    assert call[2]["is_update_data"] is False


def test_management_routes_map_to_compatibility_methods(client):
    assert client.post("/delete", json={"id": "d1", "index_names": "idx", "refresh_imm": True}).json()["success"]
    assert client.post("/get_value_collection", json={"index_name": "idx", "field_name": "platform"}).json()["values"] == ["x"]
    assert client.post("/get_unique_values", json={"index_name": "idx", "field_name": "platform", "include_doc_count": True}).json()["values"] == [{"value": "x", "doc_count": 2}]
    assert client.post("/list_file_names", json={"index_name": "idx"}).json()["total_count"] == 1
    assert client.post("/preview_delete_by_file", json={"index_name": "idx", "file_names": ["a.pdf"]}).json()["total_count"] == 1
    assert client.post("/delete_by_file", json={"index_name": "idx", "file_names": ["a.pdf"]}).json()["deleted_count"] == 1
    assert client.post("/update_by_condition", json={
        "index_name": "idx", "update_fields": {"del_flag": 1}, "conditions": [{"_id": ["d1"]}],
    }).json()["success"]
    names = [call[0] for call in lr._service.calls]
    assert names == ["delete_data", "get_unique_values", "get_unique_values", "list_file_names", "preview_delete_by_file", "delete_by_file", "update_data_value"]


def test_modify_routes_preserve_shape_and_support_injected_modifier(client):
    payload = {
        "es_index": "idx", "new_query_info": {"title": "new", "content": "a"},
        "old_query_info": {"title": "old", "content": "b"}, "search_querys": ["old"],
    }
    unavailable = client.post("/modify_knowledge", json=payload)
    assert unavailable.status_code == 200
    assert unavailable.json()["success"] is False
    lr._modifier = FakeModifier()
    direct = client.post("/modify_knowledge_direct_update", json=payload)
    assert direct.json() == {"success": True, "has_correction": True, "message": "updated", "modify_qa_infos": None}
    modified = client.post("/modify_knowledge", json=payload)
    assert modified.json()["success"] is True
    assert modified.json()["modify_qa_infos"][0]["_id"] == "d1"
    assert [name for name, _ in lr._modifier.calls] == ["direct", "modify"]


def test_old_validation_errors_are_preserved(client):
    assert client.post("/insert", json={"title": "Q"}).status_code == 422
    assert client.post("/preview_delete_by_file", json={"index_name": "idx", "file_names": [], "match_mode": "exact"}).status_code == 400
    assert client.post("/preview_delete_by_file", json={"index_name": "idx", "file_names": ["x"], "match_mode": "other"}).status_code == 400
    assert client.post("/modify_knowledge", json={"es_index": "idx", "new_query_info": {}}).status_code == 400
