from copy import deepcopy
from unittest.mock import Mock

import pytest

from kdb.retrieval.ontology.errors import OntologyError
from kdb.retrieval.ontology.service import OntologyService, describe_scope


def test_create_projection_status_and_conflict(doc, repo, service):
    doc.update(client="wayfair", product="ecommerce")
    created = service.insert_ontology({"data_json": doc})["ontology"]
    assert created["revision"] == 1
    assert created["client"] == "wayfair"
    assert "data_json" not in created
    assert service.get_ontology(created["ontology_id"], review_status="pending")["ontology"]["data_json"]["client"] == "wayfair"
    assert sum(call[0] == "insert" for call in repo.calls) == 1
    with pytest.raises(OntologyError) as caught:
        service.insert_ontology({"data_json": doc, "status": "inactive"})
    assert caught.value.code == "ONTOLOGY_NAME_CONFLICT"
    assert caught.value.details[0]["existing_ontology_id"] == created["ontology_id"]


def test_invalid_status_never_calls_repository(doc):
    repo = Mock()
    with pytest.raises(OntologyError) as caught:
        OntologyService(repo).insert_ontology({"data_json": doc, "status": "invalid"})
    assert caught.value.http_status == 400
    assert repo.mock_calls == []


def test_replace_scope_conflict_and_not_found_order(doc, repo, service):
    oid = service.insert_ontology({"data_json": doc})["ontology"]["ontology_id"]
    doc["client"] = "changed"
    with pytest.raises(OntologyError) as caught:
        service.update_ontology(oid, {"data_json": doc, "revision": 1})
    assert caught.value.code == "ONTOLOGY_SCOPE_IMMUTABLE"
    assert not any(call[0] == "replace" for call in repo.calls)
    repo.calls.clear()
    with pytest.raises(OntologyError) as caught:
        service.update_ontology("0" * 32, {"data_json": None, "revision": 1})
    assert caught.value.http_status == 404
    assert repo.calls == [("get", "0" * 32)]


def test_replace_stale_revision_and_deleted_cannot_be_replaced(doc, repo, service):
    oid = service.insert_ontology({"data_json": doc})["ontology"]["ontology_id"]
    repo.rows[oid].revision = 5
    with pytest.raises(OntologyError) as caught:
        service.update_ontology(oid, {"data_json": doc, "revision": 1})
    assert caught.value.details == [{"current_revision": 5}]
    assert caught.value.code == "ONTOLOGY_REVISION_CONFLICT"
    service.delete_ontology(oid)
    with pytest.raises(OntologyError) as caught:
        service.update_ontology_status(oid, {"status": "active", "revision": 6})
    assert caught.value.http_status == 404


def test_delete_idempotence_recreation_and_missing(doc, service):
    for _ in range(3):
        oid = service.insert_ontology({"data_json": doc})["ontology"]["ontology_id"]
        first = service.delete_ontology(oid, 1)
        second = service.delete_ontology(oid, 1)
        assert first["ontology"]["revision"] == second["ontology"]["revision"] == 2
        assert second["message"] == "本体已删除"
        assert second["ontology"]["del_flag"] == 1
        assert service.get_ontology(oid, include_deleted=True, review_status="all")["ontology"]["del_flag"] == 1
    with pytest.raises(OntologyError) as caught:
        service.delete_ontology("0" * 32)
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


def test_resolve_never_merges_and_inactive_falls_back(doc, service):
    industry = deepcopy(doc)
    industry.update(product="ecommerce", name="行业模板")
    industry["object_types"].append({"name": "行业专属", "identity": ["id"], "attributes": [{"name": "id", "data_type": "string"}]})
    service.insert_ontology({"data_json": industry, "review_status": "approved"})
    doc.update(client="wayfair", product="ecommerce")
    oid = service.insert_ontology({"data_json": doc, "status": "inactive", "review_status": "approved"})["ontology"]["ontology_id"]
    assert service.select_ontology("wayfair", "ecommerce")["scope"] == "industry"
    service.update_ontology_status(oid, {"status": "active", "revision": 1})
    chosen = service.select_ontology("wayfair", "ecommerce")["ontology"]["data_json"]
    assert len(chosen["object_types"]) == 1
    assert "outline" in service.select_ontology("wayfair", "ecommerce", include_document=False)["ontology"]
    service.delete_ontology(oid)
    assert service.select_ontology("wayfair", "ecommerce")["scope"] == "industry"


def test_list_preserves_absent_vs_empty_scope(doc, repo, service):
    service.insert_ontology({"data_json": doc, "review_status": "approved"})
    result = service.list_ontologies(client="", status="active", page=2, page_size=5)
    filters = repo.calls[-1][1]
    assert filters["client"] == "" and filters["product"] is None
    assert filters["offset"] == 5
    assert result["total"] == 1 and result["items"] == []


@pytest.mark.parametrize("page,size", [(0, 100), (1, 0), (1, 101), (True, 10), (1, "10"), (1.5, 10)])
def test_pagination_rejected_before_repository(service, repo, page, size):
    with pytest.raises(OntologyError) as caught:
        service.list_ontologies(page=page, page_size=size)
    assert caught.value.http_status == 400
    assert caught.value.message == "请求参数不合法"
    assert repo.calls == []


@pytest.mark.parametrize("review_status", ["pending", "rejected"])
def test_unreviewed_customer_falls_back_and_replacement_requires_review(doc, service, review_status):
    industry = service.insert_ontology({"data_json": dict(doc, product="retail"), "review_status": "approved"})["ontology"]
    customer_doc = dict(doc, client="customer", product="retail")
    customer = service.insert_ontology({"data_json": customer_doc, "review_status": review_status})["ontology"]
    assert service.select_ontology("customer", "retail")["ontology"]["ontology_id"] == industry["ontology_id"]
    oid = customer["ontology_id"]
    service.update_ontology(oid, {"revision": 1, "review_status": "approved"})
    assert service.select_ontology("customer", "retail")["ontology"]["ontology_id"] == oid
    updated = service.update_ontology(oid, {"revision": 2, "data_json": dict(customer_doc, description="changed")})["ontology"]
    assert (updated["status"], updated["review_status"]) == ("active", "pending")
    assert service.select_ontology("customer", "retail")["ontology"]["ontology_id"] == industry["ontology_id"]
    approved = service.update_ontology(oid, {"revision": 3, "data_json": customer_doc,
                                             "review_status": "approved"})["ontology"]
    assert approved["review_status"] == "approved" and approved["revision"] == 4
    assert service.select_ontology("customer", "retail")["ontology"]["ontology_id"] == oid


def test_invalid_review_status_does_not_write(doc):
    repo = Mock()
    with pytest.raises(OntologyError) as caught:
        OntologyService(repo).insert_ontology({"data_json": doc, "review_status": "all"})
    assert caught.value.http_status == 400
    assert repo.mock_calls == []


def test_partial_update_model_and_dict_preserve_document(doc, service, repo):
    from kdb.entrypoints.http.retrieval.ontology_models import UpdateOntologyRequest
    oid = service.insert_ontology({"data_json": doc})["ontology"]["ontology_id"]
    original = deepcopy(repo.rows[oid].data_json)
    body = UpdateOntologyRequest(ontology_id=oid, revision=1, review_status="approved")
    result = service.update_ontology(oid, body)["ontology"]
    assert result["review_status"] == "approved" and result["revision"] == 2
    assert not any(call[0] == "replace" for call in repo.calls)
    assert repo.rows[oid].data_json == original
    service.update_ontology(oid, {"revision": 2, "status": "inactive"})
    assert repo.rows[oid].review_status == "approved" and repo.rows[oid].data_json == original
    service.delete_ontology(oid)
    with pytest.raises(OntologyError) as caught:
        service.update_ontology(oid, {"revision": 4, "review_status": "rejected"})
    assert caught.value.http_status == 404
