from copy import deepcopy
from unittest.mock import Mock

import pytest

from kdb.retrieval.ontology.errors import OntologyError
from kdb.retrieval.ontology.service import OntologyService, describe_scope


def test_create_projection_status_and_conflict(doc, repo, service):
    doc.update(client="wayfair", product="ecommerce")
    created = service.create({"data_json": doc})["ontology"]
    assert created["revision"] == 1
    assert created["client"] == created["data_json"]["client"] == "wayfair"
    assert sum(call[0] == "insert" for call in repo.calls) == 1
    with pytest.raises(OntologyError) as caught:
        service.create({"data_json": doc, "status": "draft"})
    assert caught.value.code == "ONTOLOGY_NAME_CONFLICT"
    assert caught.value.details[0]["existing_ontology_id"] == created["ontology_id"]


def test_invalid_status_never_calls_repository(doc):
    repo = Mock()
    with pytest.raises(OntologyError) as caught:
        OntologyService(repo).create({"data_json": doc, "status": "invalid"})
    assert caught.value.http_status == 400
    assert repo.mock_calls == []


def test_replace_scope_conflict_and_not_found_order(doc, repo, service):
    oid = service.create({"data_json": doc})["ontology"]["ontology_id"]
    doc["client"] = "changed"
    with pytest.raises(OntologyError) as caught:
        service.replace(oid, {"data_json": doc, "revision": 1})
    assert caught.value.code == "ONTOLOGY_SCOPE_IMMUTABLE"
    assert not any(call[0] == "replace" for call in repo.calls)
    repo.calls.clear()
    with pytest.raises(OntologyError) as caught:
        service.replace("0" * 32, {"data_json": None, "revision": 1})
    assert caught.value.http_status == 404
    assert repo.calls == [("get", "0" * 32)]


def test_replace_stale_revision_and_deleted_cannot_be_replaced(doc, repo, service):
    oid = service.create({"data_json": doc})["ontology"]["ontology_id"]
    repo.rows[oid].revision = 5
    with pytest.raises(OntologyError) as caught:
        service.replace(oid, {"data_json": doc, "revision": 1})
    assert caught.value.details == [{"current_revision": 5}]
    assert caught.value.code == "ONTOLOGY_REVISION_CONFLICT"
    service.delete(oid)
    with pytest.raises(OntologyError) as caught:
        service.patch_status(oid, {"status": "active", "revision": 6})
    assert caught.value.http_status == 404


def test_delete_idempotence_recreation_and_missing(doc, service):
    for _ in range(3):
        oid = service.create({"data_json": doc})["ontology"]["ontology_id"]
        first = service.delete(oid, 1)
        second = service.delete(oid, 1)
        assert first["ontology"]["revision"] == second["ontology"]["revision"] == 2
        assert second["message"] == "already deleted"
        assert second["ontology"]["del_flag"] == 1
        assert service.get(oid, include_deleted=True)["ontology"]["del_flag"] == 1
    with pytest.raises(OntologyError) as caught:
        service.delete("0" * 32)
    assert caught.value.http_status == 404


@pytest.mark.parametrize("client,product,requested,scope,fallback", [
    ("wayfair", "ecommerce", ("wayfair", "ecommerce"), "client_product", False),
    ("wayfair", "", ("wayfair", "ecommerce"), "client", True),
    ("", "ecommerce", ("wayfair", "ecommerce"), "industry", True),
    ("", "", ("wayfair", "ecommerce"), "global", True),
    ("wayfair", "", ("wayfair", ""), "client", False),
    ("wayfair", "ecommerce", ("wayfair", ""), "client_product", True),
])
def test_scope_is_based_on_selected_row(client, product, requested, scope, fallback):
    assert describe_scope(Mock(client=client, product=product), *requested) == (scope, fallback)
    assert describe_scope(None, *requested) == ("none", True)


def test_resolve_never_merges_and_draft_falls_back(doc, service):
    industry = deepcopy(doc)
    industry.update(product="ecommerce", name="行业模板")
    industry["object_types"].append({"name": "行业专属", "identity": ["id"], "attributes": [{"name": "id", "data_type": "string"}]})
    service.create({"data_json": industry})
    doc.update(client="wayfair", product="ecommerce")
    oid = service.create({"data_json": doc, "status": "draft"})["ontology"]["ontology_id"]
    assert service.resolve("wayfair", "ecommerce")["scope"] == "industry"
    service.patch_status(oid, {"status": "active", "revision": 1})
    chosen = service.resolve("wayfair", "ecommerce")["ontology"]["data_json"]
    assert len(chosen["object_types"]) == 1
    assert "outline" in service.resolve("wayfair", "ecommerce", include_document=False)["ontology"]
    service.delete(oid)
    assert service.resolve("wayfair", "ecommerce")["scope"] == "industry"


def test_list_preserves_absent_vs_empty_scope(doc, repo, service):
    service.create({"data_json": doc})
    result = service.list(client="", status="active", page=2, page_size=5)
    filters = repo.calls[-1][1]
    assert filters["client"] == "" and filters["product"] is None
    assert filters["offset"] == 5
    assert result["total"] == 1 and result["items"] == []
