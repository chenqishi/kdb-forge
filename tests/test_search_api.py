import os

from fastapi.testclient import TestClient

from kdb.api import search_routes
from kdb.api.app import app


class _FakeService:
    def search_text(self, *args, **kwargs):
        return [
            {
                "_id": "d1",
                "_index": "demo",
                "title": "退款",
                "content": "答案",
                "data_type": "qa",
                "synonyms_title": ["退款流程"],
                "similarity": 0.9,
                "ext_info": {"source": "unit"},
            },
            {
                "_id": "d2",
                "title": "低分",
                "content": "忽略",
                "data_type": "qa",
                "similarity": 0.2,
            },
        ], 2

    def web_search(self, *args, **kwargs):
        return [
            {
                "_id": "d1",
                "score": 0.8,
                "indexes": [{"text": "退款", "embedding": [0.1]}],
                "ext_info": {"from_chat_history": True, "source": "unit"},
            }
        ], 1


def test_search_requires_basic_auth(monkeypatch):
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "tester")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "secret")
    client = TestClient(app)
    response = client.post("/search", json={"text": "退款"})
    assert response.status_code == 401


def test_search_preserves_legacy_shape_and_threshold(monkeypatch):
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "tester")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "secret")
    monkeypatch.setattr(search_routes, "_service", _FakeService())
    client = TestClient(app)
    response = client.post(
        "/search",
        auth=("tester", "secret"),
        json={"text": "退款", "score_threshold": 0.5},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["content"] == "退款|同义question:退款流程\n答案"
    assert body["results"][0]["metadata"] == {"source": "unit"}


def test_web_search_removes_vectors_and_history_field(monkeypatch):
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "tester")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "secret")
    monkeypatch.setattr(search_routes, "_service", _FakeService())
    client = TestClient(app)
    response = client.post(
        "/web_search",
        auth=("tester", "secret"),
        json={"text": "退款"},
    )
    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["indexes"] == ["退款"]
    assert "embedding" not in item
    assert "from_chat_history" not in item["ext_info"]
    assert response.json()["total_count"] == 1
