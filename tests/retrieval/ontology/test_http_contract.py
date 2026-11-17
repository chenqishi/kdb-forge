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
    response = client.post("/insert_ontology", json={"data_json": doc})
    assert response.status_code == 201
    meta = response.json()["ontology"]
    oid = meta["ontology_id"]
    assert re.fullmatch("[0-9a-f]{32}", oid)
    assert set(meta) == {"ontology_id", "client", "product", "name", "status", "revision",
                         "create_time", "update_time", "document_bytes"}
    duplicate = client.post("/insert_ontology", json={"data_json": doc})
    assert duplicate.status_code == 409
    assert duplicate.json()["details"][0]["existing_ontology_id"] == oid
    body = {"ontology_id": oid}
    full = client.post("/get_ontology", json=body).json()["ontology"]
    assert full["data_json"]["name"] == full["name"]
    assert full["document_bytes"] == meta["document_bytes"]
    document = client.post("/get_ontology", json=body, params={"view": "document"}).json()
    assert set(document) == {"success", "message", "ontology_id", "revision", "document"}
    outline = client.post("/get_ontology", json=body, params={"view": "outline"}).json()["ontology"]
    assert outline["outline"]["counts"]["object_types"] == 1
    assert "data_json" not in outline
    assert "create_time" not in outline and "document_bytes" not in outline


def test_full_crud_versions_status_and_deletion(client, doc):
    oid = client.post("/insert_ontology", json={"data_json": doc, "status": "draft"}).json()["ontology"]["ontology_id"]
    body = {"ontology_id": oid}
    doc["name"] = "改名"
    updated = client.post("/update_ontology", json=dict(body, data_json=doc, revision=1))
    assert updated.status_code == 200
    assert updated.json()["ontology"]["revision"] == 2
    assert updated.json()["ontology"]["status"] == "draft"
    assert "data_json" not in updated.json()["ontology"] and "deleted" not in updated.json()
    stale = client.post("/update_ontology", json=dict(body, data_json=doc, revision=1))
    assert stale.status_code == 409
    assert stale.json()["details"] == [{"current_revision": 2}]
    patched = client.post("/update_ontology_status", json=dict(body, status="active", revision=2))
    assert patched.json()["ontology"]["revision"] == 3
    assert patched.json()["ontology"]["status"] == "active"
    same = client.post("/update_ontology_status", json=dict(body, status="active", revision=3))
    assert same.json()["ontology"]["revision"] == 4
    assert client.post("/delete_ontology", json=dict(body, revision=3)).status_code == 409
    deleted = client.post("/delete_ontology", json=dict(body, revision=4))
    assert deleted.json()["deleted"] is True
    assert deleted.json()["ontology"]["del_flag"] == 1
    assert client.post("/delete_ontology", json=body).json()["message"] == "本体已删除"
    assert client.post("/get_ontology", json=body).status_code == 404
    assert client.post("/get_ontology", json=body, params={"include_deleted": "true"}).status_code == 200
    assert client.post("/update_ontology", json=dict(body, data_json=doc, revision=5)).status_code == 404


@pytest.mark.parametrize("path,body", [
    ("/list_ontologies?page=0", None), ("/list_ontologies?page_size=101", None),
    ("/list_ontologies?page_size=bad", None), ("/list_ontologies?deep=2", None),
    ("/list_ontologies?client=Bad", None), ("/list_ontologies?status=bad", None),
    ("/list_ontologies?include_deleted=nope", None),
    ("/get_ontology?view=bad", {"ontology_id": "0" * 32}),
    ("/get_ontology", {"ontology_id": "not-an-id"}),
    ("/get_ontology?ontology_id=" + "0" * 32, {}),
    ("/delete_ontology", {"ontology_id": "0" * 32, "revision": 0}),
    ("/delete_ontology", {"ontology_id": "0" * 32, "revision": "1"}),
])
def test_bad_queries_are_flat_400(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"
    assert response.json()["message"] == "请求参数不合法"
    assert set(response.json()) == {"success", "message", "code", "details"}


@pytest.mark.parametrize("path,extra", [("/get_ontology", {}), ("/update_ontology", {"data_json": {"schema_version": "1.0"}, "revision": 1}),
    ("/update_ontology_status", {"status": "active", "revision": 1}), ("/delete_ontology", {})])
@pytest.mark.parametrize("identifier", ["bad", "A" * 32, 123, None])
def test_ids_are_validated_in_body(client, path, extra, identifier):
    response = client.post(path, json=dict(extra, ontology_id=identifier))
    assert response.status_code == 400
    assert any(issue["path"] == "body.ontology_id" for issue in response.json()["details"])


@pytest.mark.parametrize("extra", [{"name": "外层错误"}, {"status": "bad"}, {"revision": 1}])
def test_bad_outer_body_is_400(client, doc, extra):
    response = client.post("/insert_ontology", json=dict({"data_json": doc}, **extra))
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"


def test_document_errors_and_invalid_body_json(client, doc):
    doc["client"] = "Wayfair"
    response = client.post("/insert_ontology", json={"data_json": doc})
    assert response.status_code == 422
    assert response.json()["details"][0]["reason"] == "invalid_pattern"
    response = client.post("/insert_ontology", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"


def test_meta_route_openapi_and_no_database_dependency():
    app = FastAPI()
    register_ontology_routes(app)
    def unavailable():
        raise AssertionError("meta must not construct a service")
    app.dependency_overrides[get_service] = unavailable
    client = TestClient(app)
    assert client.get("/ontology_meta").json()["limits"]["max_document_bytes"] == 1048576
    spec = client.get("/openapi.json").json()
    assert {key: set(value) for key, value in spec["paths"].items()} == {
        "/ontology_meta": {"get"}, **{path: {"post"} for path in
        ("/select_ontology", "/list_ontologies", "/insert_ontology", "/get_ontology",
         "/update_ontology", "/update_ontology_status", "/delete_ontology")}}
    for operations in spec["paths"].values():
        for operation in operations.values():
            assert operation["tags"] == ["ontology"]
            assert not any(p["in"] == "path" for p in operation.get("parameters", []))
    parameters = spec["paths"]["/list_ontologies"]["post"]["parameters"]
    assert all(p["in"] == "query" for p in parameters)
    assert next(p for p in parameters if p["name"] == "page_size")["schema"]["default"] == 100
    models = spec["components"]["schemas"]
    assert models["InsertOntologyResponse"]["properties"]["ontology"]["$ref"].endswith("/OntologyMeta")
    assert models["ListResponse"]["properties"]["items"]["items"]["$ref"].endswith("/OntologyListItem")
    assert len(models["DetailResponse"]["properties"]["ontology"]["anyOf"]) == 2
    assert len(models["SelectResponse"]["properties"]["ontology"]["anyOf"]) == 3
    assert "outline" in models["OntologyOutline"]["properties"]
    assert "document_bytes" not in models["OntologyListItem"]["properties"]
    for name in ("GetOntologyRequest", "UpdateOntologyRequest", "UpdateOntologyStatusRequest", "DeleteOntologyRequest"):
        assert models[name]["properties"]["ontology_id"]["pattern"] == "^[0-9a-f]{32}$"
    assert client.get("/ontology/meta").status_code == 404
    assert client.post("/ontology", json={}).status_code == 404
    assert client.get("/list_ontologies").status_code == 405


def test_same_name_in_other_scope_and_resolve_no_match(client, doc, repo):
    assert client.post("/select_ontology", json={}).json()["ontology"] is None
    for product in ("ecommerce", "retail"):
        doc["product"] = product
        assert client.post("/insert_ontology", json={"data_json": doc}).status_code == 201
    result = client.post("/list_ontologies").json()
    assert result["total"] == 2 and result["page_size"] == 100
    assert repo.calls[-1][1]["limit"] == 100
    assert all("data_json" not in item and "document_bytes" not in item for item in result["items"])
    response = client.post("/select_ontology", json={"product": "retail", "name": doc["name"], "include_document": False})
    assert response.json()["scope"] == "industry"
    assert "outline" in response.json()["ontology"]
    response = client.post("/select_ontology", json={"product": "retail"})
    assert "data_json" in response.json()["ontology"]
    assert "outline" not in response.json()["ontology"]


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
    @app.get("/ontology/unrelated")
    def other(value: int):
        raise OntologyError("ONTOLOGY_NOT_FOUND", 404, "missing")
    app.get("/tagged-elsewhere", tags=["ontology"])(other)
    register_ontology_routes(app)
    client = TestClient(app)
    assert client.get("/ontology/unrelated?value=bad").status_code == 418
    assert client.get("/ontology/unrelated?value=1").json() == {"detail": "missing"}
    assert client.get("/tagged-elsewhere?value=bad").status_code == 400
    assert client.get("/tagged-elsewhere?value=1").json()["code"] == "ONTOLOGY_NOT_FOUND"
    assert client.post("/list_ontologies?page=bad").status_code == 400


def test_proxy_prefix_keeps_flat_request_and_document_errors(service, doc):
    app = FastAPI()
    register_ontology_routes(app)
    app.dependency_overrides[get_service] = lambda: service
    client = TestClient(app, root_path="/test-gateway")
    bad_id = client.post("/test-gateway/get_ontology", json={"ontology_id": "bad"})
    assert bad_id.status_code == 400 and bad_id.json()["code"] == "ONTOLOGY_BAD_REQUEST"
    doc["client"] = "Bad"
    bad_doc = client.post("/test-gateway/insert_ontology", json={"data_json": doc})
    assert bad_doc.status_code == 422 and bad_doc.json()["code"] == "ONTOLOGY_VALIDATION_FAILED"


def test_db_unavailable_is_not_empty_success(client, repo, monkeypatch):
    def fail(*args):
        raise OntologyError("ONTOLOGY_DB_UNAVAILABLE", 503, "不可用")
    monkeypatch.setattr(repo, "select_ontology", fail)
    response = client.post("/select_ontology", json={})
    assert response.status_code == 503
    assert response.json()["success"] is False
