from copy import deepcopy
import json
import sys

import pytest

from kdb.retrieval.ontology.errors import OntologyError
from kdb.retrieval.ontology.validation import document_size, validate_document


def assert_issue(doc, reason, path, code="ONTOLOGY_VALIDATION_FAILED", status=422):
    with pytest.raises(OntologyError) as caught:
        validate_document(doc)
    error = caught.value
    assert (error.http_status, error.code) == (status, code)
    assert any(d.get("reason") == reason and d.get("path") == path for d in error.details), error.details
    return error


def test_minimal_string_normalization_and_projection(doc):
    doc.update(name=" 示例 ", client=" wayfair ", alias_name=[" foo "])
    vd = validate_document(json.dumps(doc))
    assert vd.document_bytes == document_size(vd.document)
    assert (vd.name, vd.client, vd.alias_name) == ("示例", "wayfair", ["foo"])
    assert vd.document["product"] == vd.product == ""
    assert vd.document["language"] == "zh-CN"
    assert vd.document["relations"] == []
    assert doc["name"] == " 示例 "


@pytest.mark.parametrize("raw,reason", [("{", "invalid_json"), ("[]", "invalid_type"),
                                       ([], "invalid_type"), (None, "invalid_type"), (3, "invalid_type")])
def test_invalid_raw(raw, reason):
    assert_issue(raw, reason, "$")


def test_schema_version_and_early_exit(doc):
    doc.pop("schema_version")
    assert_issue(doc, "missing_required", "schema_version")
    doc.update(schema_version="2.0", revision=1)
    assert_issue(doc, "unsupported_schema_version", "schema_version", "ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED")


def test_unknown_and_reserved_fields(doc):
    doc["foo"] = 1
    assert_issue(doc, "unknown_field", "foo")
    doc["revision"] = 1
    error = assert_issue(doc, "reserved_field", "revision", "ONTOLOGY_RESERVED_FIELD")
    assert error.details[0]["reason"] == "reserved_field"
    doc.pop("foo"); doc.pop("revision")
    doc["extensions"] = {"revision": 4, "nested": {"status": "anything"}}
    assert validate_document(doc).document["extensions"]["revision"] == 4
    doc["llm_hints"] = {"nested": [{"id": "reserved"}]}
    assert_issue(doc, "reserved_field", "llm_hints.nested[0].id", "ONTOLOGY_RESERVED_FIELD")


def test_audit_status_is_row_control_except_inside_extensions(doc):
    doc["audit_status"] = "approved"
    assert_issue(doc, "reserved_field", "audit_status", "ONTOLOGY_RESERVED_FIELD")
    del doc["audit_status"]
    doc["llm_hints"] = {"audit_status": "approved"}
    assert_issue(doc, "reserved_field", "llm_hints.audit_status", "ONTOLOGY_RESERVED_FIELD")
    del doc["llm_hints"]
    doc["extensions"] = {"audit_status": "domain-specific"}
    assert validate_document(doc).document["extensions"]["audit_status"] == "domain-specific"


def test_casefold_duplicate_class_attribute_enum_and_alias(doc):
    node = doc["object_types"][0]
    node["name"] = "Ｏｒｄｅｒ"
    doc["object_types"].append(dict(deepcopy(node), name="order "))
    assert_issue(doc, "duplicate_name", "object_types[1].name")
    doc["object_types"].pop()
    node["attributes"].append(deepcopy(node["attributes"][0]))
    assert_issue(doc, "duplicate_name", "object_types[0].attributes[1].name")
    node["attributes"].pop()
    doc["value_sets"] = [{"name": "状态", "values": [{"value": "Paid", "label": "支付"}, {"value": "paid", "label": "支付"}]}]
    assert_issue(doc, "duplicate_name", "value_sets[0].values[1].value")
    doc["value_sets"] = []
    doc["alias_name"] = ["订单", "订单 "]
    assert_issue(doc, "duplicate_alias", "alias_name[1]")


@pytest.mark.parametrize("changes,reason,field", [
    ({"data_type": "enum"}, "missing_required", "value_set"),
    ({"data_type": "object"}, "missing_required", "ref"),
    ({"data_type": "array"}, "missing_required", "item_type"),
    ({"data_type": "array", "item_type": "enum"}, "missing_required", "value_set"),
    ({"data_type": "array", "item_type": "object"}, "missing_required", "ref"),
    ({"data_type": "string", "value_set": "missing"}, "invalid_field_combination", "value_set"),
    ({"data_type": "string", "ref": "消息"}, "invalid_field_combination", "ref"),
    ({"data_type": "string", "item_type": "integer"}, "invalid_field_combination", "item_type"),
    ({"data_type": "enum", "value_set": "missing"}, "unresolved_reference", "value_set"),
    ({"data_type": "object", "ref": "missing"}, "unresolved_reference", "ref"),
])
def test_attribute_combinations_and_references(doc, changes, reason, field):
    doc["object_types"][0]["attributes"][0].update(changes)
    assert_issue(doc, reason, "object_types[0].attributes[0]." + field)


def test_identity_and_folded_references(doc):
    node = doc["object_types"][0]
    node["identity"] = ["missing"]
    assert_issue(doc, "unresolved_reference", "object_types[0].identity[0]")
    node.update(name="Order", identity=["id"])
    node["attributes"][0]["name"] = "ＩＤ"
    node["attributes"].append({"name": "parent", "data_type": "array", "item_type": "object", "ref": "order"})
    doc["value_sets"] = [{"name": "Status", "values": [{"value": "PAID", "label": "支付"}]}]
    doc["terms"] = [{"name": str(i), "description": "说明", "refers_to": ref}
                    for i, ref in enumerate(["order", "status", "ORDER.id", "status.paid"])]
    validated = validate_document(doc).document
    assert validated["terms"][2]["refers_to"] == "ORDER.id"
    assert validated["object_types"][0]["attributes"][1]["ref"] == "order"


@pytest.mark.parametrize("name", ["订单.明细", "bad\x00name", "bad\x7fname"])
def test_invalid_names(doc, name):
    doc["object_types"][0]["name"] = name
    assert_issue(doc, "invalid_pattern", "object_types[0].name")


def test_scope_is_not_silently_lowercased_and_types_are_strict(doc):
    doc["client"] = "Wayfair"
    assert_issue(doc, "invalid_pattern", "client")
    doc["client"] = ""
    doc["object_types"][0]["attributes"][0]["required"] = "false"
    assert_issue(doc, "invalid_type", "object_types[0].attributes[0].required")


def test_size_checks_warning_and_free_dict_caps(doc, caplog):
    oversized = dict(doc, extensions={"text": "中" * 400000})
    with pytest.raises(OntologyError) as caught:
        validate_document(oversized)
    assert caught.value.http_status == 413
    assert caught.value.details[0]["actual_bytes"] > 1048576
    doc["object_types"][0]["attributes"] = [{"name": "消息ID" if i == 0 else "字段%s" % i,
        "description": "中" * 500, "data_type": "string"} for i in range(200)]
    vd = validate_document(doc)
    assert 300000 < vd.document_bytes < 1048576
    assert "bytes=" in caplog.text
    doc["llm_hints"] = {"text": "x" * 65536}
    assert_issue(doc, "too_long", "llm_hints")


def test_errors_are_deterministic_and_bounded(doc):
    doc["terms"] = [{"name": str(i), "description": "术语", "refers_to": "missing"} for i in range(60)]
    first = assert_issue(doc, "unresolved_reference", "terms[0].refers_to")
    second = assert_issue(doc, "unresolved_reference", "terms[0].refers_to")
    assert len(first.details) == 50
    assert first.details == second.details


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()])
def test_non_json_values_are_rejected(doc, value):
    doc["extensions"] = {"value": value}
    assert_issue(doc, "invalid_json", "$")


def test_deep_json_produces_validation_error_not_recursion_crash(doc):
    nested = {}
    for _ in range(sys.getrecursionlimit() + 10):
        nested = {"nested": nested}
    doc["extensions"] = nested
    assert_issue(doc, "invalid_json", "$")
