"""Restricted local compatibility for the retrieval-only HTTP application."""

import pytest
from fastapi.testclient import TestClient

from kdb.api import search_routes
from kdb.api.retrieval_app import app


class _FakeService:
    def __init__(self):
        self.calls = 0

    def search_text(self, *args, **kwargs):
        self.calls += 1
        return [{"_id": "1", "_index": "mercado", "title": "Question",
                 "content": "Answer", "similarity": 0.9}], 1

    def web_search(self, *args, **kwargs):
        self.calls += 1
        return [{"_id": "1", "score": 0.9}], 1


@pytest.fixture(autouse=True)
def _auth_and_fake_service(monkeypatch):
    monkeypatch.setenv("KDB_SEARCH_BASIC_USER", "tester")
    monkeypatch.setenv("KDB_SEARCH_BASIC_PASSWORD", "secret")
    monkeypatch.delenv("KDB_SEARCH_ALLOW_LOOPBACK", raising=False)
    service = _FakeService()
    monkeypatch.setattr(search_routes, "_service", service)
    return service


@pytest.mark.parametrize("route", ["/search", "/web_search"])
def test_default_requires_auth_even_for_loopback(route, _auth_and_fake_service):
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post(route, json={"text": "Question"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"
    assert _auth_and_fake_service.calls == 0


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
@pytest.mark.parametrize("route", ["/search", "/web_search"])
def test_enabled_direct_loopback_can_search(host, route, monkeypatch,
                                           _auth_and_fake_service):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=(host, 50000))
    response = client.post(route, json={"text": "Question"})
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert _auth_and_fake_service.calls == 1


@pytest.mark.parametrize("headers", [
    {"Forwarded": "for=198.51.100.1"},
    {"X-Forwarded-For": "198.51.100.1"},
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Forwarded-Proto": "https"},
    {"X-Forwarded-Host": "example.test"},
    {"X-Real-IP": "198.51.100.1"},
    {"X-Real-IP": ""},
    {"Via": "1.1 proxy"},
    {"CF-Connecting-IP": "198.51.100.1"},
    {"True-Client-IP": "198.51.100.1"},
])
def test_proxy_headers_prevent_loopback_bypass(headers, monkeypatch,
                                              _auth_and_fake_service):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post("/search", headers=headers, json={"text": "Question"})
    assert response.status_code == 401
    assert _auth_and_fake_service.calls == 0


@pytest.mark.parametrize("host", ["198.51.100.1", "10.0.0.1", "127.0.0.2",
                                  "::ffff:127.0.0.1"])
def test_enabled_external_peer_requires_auth(host, monkeypatch,
                                           _auth_and_fake_service):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=(host, 50000))
    response = client.post("/search", json={"text": "Question"})
    assert response.status_code == 401
    assert _auth_and_fake_service.calls == 0


@pytest.mark.parametrize("allow_loopback", [None, "1"])
@pytest.mark.parametrize("route", ["/search", "/web_search"])
def test_valid_basic_still_works_through_proxy(route, allow_loopback, monkeypatch,
                                             _auth_and_fake_service):
    if allow_loopback is not None:
        monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", allow_loopback)
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post(route, auth=("tester", "secret"),
                           headers={"X-Forwarded-For": "198.51.100.1"},
                           json={"text": "Question"})
    assert response.status_code == 200
    assert _auth_and_fake_service.calls == 1


@pytest.mark.parametrize("auth", [("tester", "wrong"), ("wrong", "secret")])
def test_wrong_basic_is_rejected_even_on_enabled_loopback(auth, monkeypatch,
                                                         _auth_and_fake_service):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post("/search", auth=auth, json={"text": "Question"})
    assert response.status_code == 401
    assert _auth_and_fake_service.calls == 0


@pytest.mark.parametrize("authorization", ["Bearer token", "Basic invalid", ""])
def test_non_basic_or_malformed_auth_cannot_take_loopback_bypass(
    authorization, monkeypatch, _auth_and_fake_service,
):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", "1")
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post("/search", headers={"Authorization": authorization},
                           json={"text": "Question"})
    assert response.status_code == 401
    assert _auth_and_fake_service.calls == 0


@pytest.mark.parametrize("flag", ["0", "true", "yes"])
def test_loopback_flag_requires_explicit_one(flag, monkeypatch,
                                           _auth_and_fake_service):
    monkeypatch.setenv("KDB_SEARCH_ALLOW_LOOPBACK", flag)
    client = TestClient(app, client=("127.0.0.1", 50000))
    assert client.post("/search", json={"text": "Question"}).status_code == 401
    assert _auth_and_fake_service.calls == 0
