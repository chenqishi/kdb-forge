import json
from unittest.mock import Mock

import pytest

from kdb.entrypoints.cli.tools.ontology_clone import main
from kdb.retrieval.ontology.errors import OntologyError

ARGS = ["--source-client", "", "--source-product", "ecommerce", "--target-client", "wayfair"]


def test_clone_dry_run_is_active_pending_and_does_not_change_source(doc, service, repo, capsys):
    doc.update(product="ecommerce")
    source = service.insert_ontology({"data_json": doc, "audit_status": "approved"})["ontology"]
    assert main(ARGS + ["--dry-run"], service=service) == 0
    assert len(repo.rows) == 1
    assert json.loads(capsys.readouterr().out)["audit_status"] == "pending"
    assert main(ARGS, service=service) == 0
    created = json.loads(capsys.readouterr().out)["ontology"]
    assert created["client"] == "wayfair" and created["status"] == "active" and created["audit_status"] == "pending"
    unchanged = service.get_ontology(source["ontology_id"])["ontology"]
    assert all(unchanged[key] == value for key, value in source.items())
    assert unchanged["data_json"]["client"] == ""
    assert unchanged["data_json"]["product"] == "ecommerce"
    assert "data_json" not in created
    assert main(ARGS, service=service) == 3
    assert json.loads(capsys.readouterr().err)["code"] == "ONTOLOGY_NAME_CONFLICT"


@pytest.mark.parametrize("code,status,expected", [("ONTOLOGY_DB_UNAVAILABLE", 503, 5),
                                                 ("ONTOLOGY_VALIDATION_FAILED", 422, 4)])
def test_clone_error_exit_codes(code, status, expected, capsys):
    service = Mock()
    service.select_ontology.side_effect = OntologyError(code, status, "failed")
    assert main(ARGS, service=service) == expected
    assert json.loads(capsys.readouterr().err)["code"] == code


def test_clone_absent_source_and_empty_target(service, capsys):
    assert main(ARGS, service=service) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "ONTOLOGY_NOT_FOUND"
    assert main(ARGS[:-1] + [""], service=service) == 4


def test_clone_accepts_audit_status_argument(doc, service, capsys):
    doc.update(product="ecommerce")
    service.insert_ontology({"data_json": doc, "audit_status": "approved"})
    assert main(ARGS + ["--audit-status", "rejected", "--status", "inactive"], service=service) == 0
    created = json.loads(capsys.readouterr().out)["ontology"]
    assert created["audit_status"] == "rejected" and created["status"] == "inactive"
    assert "review_status" not in created
