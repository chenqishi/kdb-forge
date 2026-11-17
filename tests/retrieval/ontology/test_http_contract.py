from copy import deepcopy
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from kdb.entrypoints.http.retrieval.ontology_routes import get_service, register_ontology_routes
from kdb.retrieval.ontology.errors import OntologyError


@pytest.fixture
def client(service):
    app = FastAPI()
    register_ontology_routes(app)
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


def test_create_conflict_and_three_views(client, doc):
    response = client.post("/ontology", json={"data_json": doc})
    assert response.status_code == 201
    full = response.json()["ontology"]
    oid = full["ontology_id"]
    assert re.fullmatch("[0-9a-f]{32}", oid)
    assert full["data_json"]["name"] == full["name"]
    duplicate = client.post("/ontology", json={"data_json": doc})
    assert duplicate.status_code == 409
    assert duplicate.json()["details"][0]["existing_ontology_id"] == oid
    path = "/ontology/" + oid
    assert client.get(path).json()["ontology"]["document_bytes"] > 0
    document = client.get(path, params={"view": "document"}).json()
    assert set(document) == {"success", "message", "ontology_id", "revision", "document"}
    outline = client.get(path, params={"view": "outline"}).json()["ontology"]
    assert outline["outline"]["counts"]["object_types"] == 1
    assert "data_json" not in outline


def test_full_crud_versions_status_and_deletion(client, doc):
    oid = client.post("/ontology", json={"data_json": doc, "status": "draft"}).json()["ontology"]["ontology_id"]
    path = "/ontology/" + oid
    doc["name"] = "改名"
    updated = client.put(path, json={"data_json": doc, "revision": 1})
    assert updated.status_code == 200
    assert updated.json()["ontology"]["revision"] == 2
    assert updated.json()["ontology"]["status"] == "draft"
    assert "data_json" not in updated.json()["ontology"]
    assert "deleted" not in updated.json()
    stale = client.put(path, json={"data_json": doc, "revision": 1})
    assert stale.status_code == 409
    assert stale.json()["details"] == [{"current_revision": 2}]
    patched = client.patch(path, json={"status": "active", "revision": 2})
    assert patched.json()["ontology"]["revision"] == 3
    assert patched.json()["ontology"]["status"] == "active"
    same = client.patch(path, json={"status": "active", "revision": 3})
    assert same.json()["ontology"]["revision"] == 4
    assert client.delete(path, params={"revision": 3}).status_code == 409
    deleted = client.delete(path, params={"revision": 4})
    assert deleted.json()["deleted"] is True
    assert deleted.json()["ontology"]["del_flag"] == 1
    assert client.delete(path).json()["message"] == "already deleted"
    assert client.get(path).status_code == 404
    assert client.get(path, params={"include_deleted": "true"}).status_code == 200
    assert client.put(path, json={"data_json": doc, "revision": 5}).status_code == 404


@pytest.mark.parametrize("path", ["/ontology?page=0", "/ontology?page_size=101", "/ontology?deep=2",
                                  "/ontology?client=Bad", "/ontology?status=bad", "/ontology?include_deleted=nope",
                                  "/ontology/" + "0" * 32 + "?view=bad", "/ontology/not-an-id"])
def test_bad_queries_are_flat_400(client, path):
    response = client.get(path)
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"
    assert set(response.json()) == {"success", "message", "code", "details"}


@pytest.mark.parametrize("extra", [{"name": "外层错误"}, {"status": "bad"}, {"revision": 1}])
def test_bad_outer_body_is_400(client, doc, extra):
    response = client.post("/ontology", json=dict({"data_json": doc}, **extra))
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"


def test_document_errors_and_invalid_body_json(client, doc):
    doc["client"] = "Wayfair"
    response = client.post("/ontology", json={"data_json": doc})
    assert response.status_code == 422
    assert response.json()["details"][0]["reason"] == "invalid_pattern"
    response = client.post("/ontology", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"


def test_meta_route_openapi_and_no_database_dependency():
    app = FastAPI()
    register_ontology_routes(app)
    def unavailable():
        raise AssertionError("meta must not construct a service")
    app.dependency_overrides[get_service] = unavailable
    client = TestClient(app)
    assert client.get("/ontology/meta").json()["limits"]["max_document_bytes"] == 1048576
    paths = client.get("/openapi.json").json()["paths"]
    assert {key: set(value) for key, value in paths.items()} == {
        "/ontology/meta": {"get"}, "/ontology/resolve": {"post"},
        "/ontology": {"get", "post"}, "/ontology/{ontology_id}": {"get", "put", "patch", "delete"}}
    ordered = [r.path for r in app.routes]
    assert ordered.index("/ontology/meta") < ordered.index("/ontology/{ontology_id}")


def test_same_name_in_other_scope_and_resolve_no_match(client, doc):
    assert client.post("/ontology/resolve", json={}).json()["ontology"] is None
    for product in ("ecommerce", "retail"):
        doc["product"] = product
        assert client.post("/ontology", json={"data_json": doc}).status_code == 201
    result = client.get("/ontology").json()
    assert result["total"] == 2
    assert all("data_json" not in item for item in result["items"])
    response = client.post("/ontology/resolve", json={"product": "retail", "name": doc["name"], "include_document": False})
    assert response.json()["scope"] == "industry"
    assert "outline" in response.json()["ontology"]


def test_non_ontology_validation_and_custom_handler_are_preserved():
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.get("/other")
    def other(value: int):
        return value
    register_ontology_routes(app)
    response = TestClient(app).get("/other", params={"value": "bad"})
    assert response.status_code == 422 and "detail" in response.json()
    custom = FastAPI()
    @custom.exception_handler(RequestValidationError)
    async def handler(request, exc):
        return JSONResponse({"original": True}, status_code=418)
    custom.get("/other")(other)
    register_ontology_routes(custom)
    assert TestClient(custom).get("/other?value=bad").status_code == 418


def test_sync_validation_handler_and_ontology_business_error_are_scoped():
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    app = FastAPI()
    @app.exception_handler(RequestValidationError)
    def custom_handler(request, exc):
        return JSONResponse({"original": True}, status_code=418)
    @app.get("/other")
    def other(value: int):
        raise OntologyError("ONTOLOGY_NOT_FOUND", 404, "missing")
    register_ontology_routes(app)
    client = TestClient(app)
    assert client.get("/other?value=bad").status_code == 418
    assert client.get("/other?value=1").json() == {"detail": "missing"}
    assert client.get("/ontology?page=bad").status_code == 400


def test_db_unavailable_is_not_empty_success(client, repo, monkeypatch):
    def fail(*args):
        raise OntologyError("ONTOLOGY_DB_UNAVAILABLE", 503, "不可用")
    monkeypatch.setattr(repo, "resolve", fail)
    response = client.post("/ontology/resolve", json={})
    assert response.status_code == 503
    assert response.json()["success"] is False
