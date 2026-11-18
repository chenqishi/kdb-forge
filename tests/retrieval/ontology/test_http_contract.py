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
    response = client.post("/insert_ontology", json={"data_json": doc, "review_status": "approved"})
    assert response.status_code == 201
    meta = response.json()["ontology"]
    oid = meta["ontology_id"]
    assert re.fullmatch("[0-9a-f]{32}", oid)
    assert set(meta) == {"ontology_id", "client", "product", "name", "status", "review_status", "revision",
                         "create_time", "update_time", "document_bytes"}
    duplicate = client.post("/insert_ontology", json={"data_json": doc, "review_status": "approved"})
    assert duplicate.status_code == 409
    assert duplicate.json()["details"][0]["existing_ontology_id"] == oid
    body = {"ontology_id": oid}
    full = client.post("/get_ontology", json=body).json()["ontology"]
    assert full["data_json"]["name"] == full["name"]
    assert full["document_bytes"] == meta["document_bytes"]
    document = client.post("/get_ontology", json=body, params={"view": "document"}).json()
    assert set(document) == {"success", "message", "ontology_id", "status", "review_status", "revision", "document"}
    outline = client.post("/get_ontology", json=body, params={"view": "outline"}).json()["ontology"]
    assert outline["outline"]["counts"]["object_types"] == 1
    assert "data_json" not in outline
    assert "create_time" not in outline and "document_bytes" not in outline


def test_full_crud_versions_status_and_deletion(client, doc):
    oid = client.post("/insert_ontology", json={"data_json": doc, "status": "inactive"}).json()["ontology"]["ontology_id"]
    body = {"ontology_id": oid}
    doc["name"] = "改名"
    updated = client.post("/update_ontology", json=dict(body, data_json=doc, revision=1))
    assert updated.status_code == 200
    assert updated.json()["ontology"]["revision"] == 2
    assert updated.json()["ontology"]["status"] == "inactive"
    assert "data_json" not in updated.json()["ontology"] and "deleted" not in updated.json()
    stale = client.post("/update_ontology", json=dict(body, data_json=doc, revision=1))
    assert stale.status_code == 409
    assert stale.json()["details"] == [{"current_revision": 2}]
    patched = client.post("/update_ontology_status", json=dict(body, status="active", review_status="approved", revision=2))
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
    response = client.post("/insert_ontology", json={"data_json": doc, "review_status": "approved"})
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
        assert client.post("/insert_ontology", json={"data_json": doc, "review_status": "approved"}).status_code == 201
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
    bad_doc = client.post("/test-gateway/insert_ontology", json={"data_json": doc, "review_status": "approved"})
    assert bad_doc.status_code == 422 and bad_doc.json()["code"] == "ONTOLOGY_VALIDATION_FAILED"


def test_db_unavailable_is_not_empty_success(client, repo, monkeypatch):
    def fail(*args):
        raise OntologyError("ONTOLOGY_DB_UNAVAILABLE", 503, "不可用")
    monkeypatch.setattr(repo, "select_ontology", fail)
    response = client.post("/select_ontology", json={})
    assert response.status_code == 503
    assert response.json()["success"] is False


def test_defaults_review_workflow_and_document_edit_require_review(client, doc):
    meta = client.post("/insert_ontology", json={"data_json": doc}).json()["ontology"]
    assert (meta["status"], meta["review_status"], meta["revision"]) == ("active", "pending", 1)
    body = {"ontology_id": meta["ontology_id"]}
    assert client.post("/list_ontologies").json()["total"] == 0
    assert client.post("/select_ontology", json={}).json()["ontology"] is None
    for view in ("full", "document", "outline"):
        assert client.post("/get_ontology", json=body, params={"view": view}).status_code == 404
        pending = client.post("/get_ontology", json=body, params={"view": view, "review_status": "pending"})
        assert pending.status_code == 200
        assert (pending.json() if view == "document" else pending.json()["ontology"])["review_status"] == "pending"
    approved = client.post("/update_ontology_status", json=dict(body, revision=1, review_status="approved"))
    assert approved.status_code == 200
    assert approved.json()["ontology"]["status"] == "active"
    assert approved.json()["ontology"]["revision"] == 2
    assert client.post("/get_ontology", json=body).status_code == 200
    assert client.post("/select_ontology", json={}).json()["ontology"]["ontology_id"] == body["ontology_id"]
    disabled = client.post("/update_ontology_status", json=dict(body, revision=2, status="inactive"))
    assert disabled.json()["ontology"]["review_status"] == "approved"
    assert client.post("/list_ontologies").json()["total"] == 1
    assert client.post("/select_ontology", json={}).json()["ontology"] is None
    doc["description"] = "内容修改必须重新审核"
    updated = client.post("/update_ontology", json=dict(body, revision=3, data_json=doc)).json()["ontology"]
    assert (updated["status"], updated["review_status"], updated["revision"]) == ("inactive", "pending", 4)
    assert client.post("/get_ontology", json=body).status_code == 404
    assert client.post("/list_ontologies").json()["total"] == 0
    assert client.post("/update_ontology_status", json=dict(body, revision=3, review_status="approved")).status_code == 409
    rejected = client.post("/update_ontology_status", json=dict(body, revision=4, review_status="rejected"))
    assert rejected.json()["ontology"]["revision"] == 5
    assert client.post("/get_ontology", json=body, params={"review_status": "rejected"}).status_code == 200
    assert client.post("/delete_ontology", json=dict(body, revision=5)).status_code == 200
    assert client.post("/get_ontology", json=body, params={"include_deleted": True}).status_code == 404
    assert client.post("/get_ontology", json=body, params={"include_deleted": True, "review_status": "all"}).status_code == 200


@pytest.mark.parametrize("status", ["active", "inactive"])
@pytest.mark.parametrize("review_status", ["pending", "approved", "rejected"])
@pytest.mark.parametrize("deleted", [False, True])
def test_query_filters_are_independent(client, doc, status, review_status, deleted):
    meta = client.post("/insert_ontology", json={"data_json": doc, "status": status,
                                                "review_status": review_status}).json()["ontology"]
    body = {"ontology_id": meta["ontology_id"]}
    if deleted:
        assert client.post("/delete_ontology", json=body).status_code == 200
    expected = not deleted and review_status == "approved"
    assert client.post("/get_ontology", json=body).status_code == (200 if expected else 404)
    assert client.post("/list_ontologies").json()["total"] == int(expected)
    chosen = client.post("/select_ontology", json={}).json()["ontology"]
    assert (chosen is not None) == (expected and status == "active")
    assert client.post("/list_ontologies", params={"review_status": "all"}).json()["total"] == int(not deleted)
    assert client.post("/list_ontologies", params={"include_deleted": True}).json()["total"] == int(review_status == "approved")
    for requested in ("pending", "approved", "rejected", "all"):
        params = {"review_status": requested, "include_deleted": True}
        visible = requested in (review_status, "all")
        assert client.post("/get_ontology", json=body, params=params).status_code == (200 if visible else 404)
        result = client.post("/list_ontologies", params=dict(params, status=status)).json()
        assert result["total"] == int(visible)
        if visible:
            assert result["items"][0]["review_status"] == review_status


@pytest.mark.parametrize("path,payload,params", [
    ("/insert_ontology", {"status": "draft"}, {}),
    ("/insert_ontology", {"review_status": "all"}, {}),
    ("/insert_ontology", {"review_status": True}, {}),
    ("/update_ontology", {"review_status": "bad"}, {}),
    ("/update_ontology_status", {"review_status": "bad"}, {}),
    ("/update_ontology_status", {}, {}),
    ("/update_ontology_status", {"status": None, "review_status": None}, {}),
    ("/get_ontology", {}, {"review_status": "bad"}),
    ("/list_ontologies", {}, {"review_status": "bad"}),
])
def test_invalid_review_and_empty_status_updates_are_400(client, doc, path, payload, params):
    if path == "/insert_ontology":
        body = dict(data_json=doc, **payload)
    elif path == "/update_ontology":
        body = dict(ontology_id="0" * 32, revision=1, data_json=doc, **payload)
    elif path == "/update_ontology_status":
        body = dict(ontology_id="0" * 32, revision=1, **payload)
    else:
        body = {"ontology_id": "0" * 32} if path == "/get_ontology" else None
    response = client.post(path, json=body, params=params)
    assert response.status_code == 400
    assert response.json()["code"] == "ONTOLOGY_BAD_REQUEST"


def test_openapi_exposes_review_defaults_and_all_response_states(client):
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    props = schemas["InsertOntologyRequest"]["properties"]
    assert props["status"]["default"] == "active"
    assert props["review_status"]["default"] == "pending"
    for name in ("OntologyMeta", "OntologyFull", "OntologyOutline", "OntologyListItem", "SelectedOntologyDocument", "DocumentResponse"):
        assert schemas[name]["properties"]["review_status"]["enum"] == ["pending", "approved", "rejected"]
    for path in ("/get_ontology", "/list_ontologies"):
        review = next(p for p in spec["paths"][path]["post"]["parameters"] if p["name"] == "review_status")
        assert review["in"] == "query" and review["schema"]["default"] == "approved"
    meta = client.get("/ontology_meta").json()
    assert meta["status_values"] == ["active", "inactive"]
    assert meta["review_status_values"] == ["pending", "approved", "rejected"]
    assert "review_status" in meta["reserved_fields"]
