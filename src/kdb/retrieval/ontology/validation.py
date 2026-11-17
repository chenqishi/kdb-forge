"""Pure document validation: size, version, reserved keys, shape, names and references."""
import json
import logging
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from pydantic import ValidationError

from .errors import (OntologyError, ONTOLOGY_PAYLOAD_TOO_LARGE,
                     ONTOLOGY_RESERVED_FIELD, ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED,
                     ONTOLOGY_VALIDATION_FAILED)
from .models import OntologyDocument
from .schema import (MAX_DOCUMENT_BYTES, MAX_ERRORS, RESERVED_FIELDS,
                     RESERVED_SCAN_SKIP, SCHEMA_VERSION, WARN_DOCUMENT_BYTES)

logger = logging.getLogger(__name__)
ERROR_REASONS = {
    "missing": "missing_required", "string_too_long": "too_long", "too_long": "too_long",
    "string_too_short": "too_short", "too_short": "too_short",
    "string_pattern_mismatch": "invalid_pattern", "literal_error": "invalid_enum_value",
    "extra_forbidden": "unknown_field", "json_invalid": "invalid_json",
}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    reason: str
    message: str


@dataclass(frozen=True)
class ValidatedDocument:
    document: Dict[str, Any]
    client: str
    product: str
    name: str
    alias_name: List[str]
    description: str
    document_bytes: int


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def document_size(value: Any) -> int:
    return len(compact_json(value).encode("utf-8"))


def issue_path(loc) -> str:
    path = ""
    for part in loc:
        path += "[%s]" % part if isinstance(part, int) else ("." if path else "") + str(part)
    return path or "$"


def pydantic_issues(errors) -> List[Dict[str, str]]:
    return [{"path": issue_path(e["loc"]),
             "reason": ERROR_REASONS.get(e["type"], "invalid_type"),
             "message": e["msg"]} for e in errors[:MAX_ERRORS]]


def nfkc_casefold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _strip(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {key: _strip(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def _check_size(size):
    if size > MAX_DOCUMENT_BYTES:
        raise OntologyError(ONTOLOGY_PAYLOAD_TOO_LARGE, 413, "文档超过 1MB 上限",
                            [{"actual_bytes": size, "limit_bytes": MAX_DOCUMENT_BYTES}])


def _fail(issues, reserved=False):
    if issues:
        details = [asdict(i) if isinstance(i, ValidationIssue) else i for i in issues[:MAX_ERRORS]]
        raise OntologyError(ONTOLOGY_RESERVED_FIELD if reserved else ONTOLOGY_VALIDATION_FAILED,
                            422, "文档校验未通过：%s 处错误" % len(details), details)


def _reserved(value, issues, loc=()):
    if len(issues) >= MAX_ERRORS:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in RESERVED_SCAN_SKIP:
                continue
            if key in RESERVED_FIELDS:
                issues.append(ValidationIssue(issue_path(loc + (key,)), "reserved_field", "文档不能包含行控制字段"))
            _reserved(item, issues, loc + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reserved(item, issues, loc + (index,))


def _nodes(doc):
    yield doc, ""
    for collection in ("object_types", "relations", "value_sets", "rules", "terms"):
        for i, node in enumerate(doc[collection]):
            path = "%s[%s]" % (collection, i)
            yield node, path
            child = "attributes" if collection == "object_types" else "values" if collection == "value_sets" else None
            if child:
                for j, item in enumerate(node[child]):
                    yield item, "%s.%s[%s]" % (path, child, j)


def _unique(items, field, path, issues, alias=False):
    seen = {}
    for i, node in enumerate(items):
        raw = node if alias else node[field]
        key = nfkc_casefold(raw)
        current = "%s[%s]%s" % (path, i, "" if alias else "." + field)
        if key in seen:
            issues.append(ValidationIssue(current, "duplicate_alias" if alias else "duplicate_name",
                                           "与 %s 折叠后同名：%s" % (seen[key], raw)))
        else:
            seen[key] = current


def _uniqueness(doc, issues):
    for collection in ("object_types", "relations", "value_sets", "rules", "terms"):
        _unique(doc[collection], "name", collection, issues)
    for i, node in enumerate(doc["object_types"]):
        _unique(node["attributes"], "name", "object_types[%s].attributes" % i, issues)
    for i, node in enumerate(doc["value_sets"]):
        _unique(node["values"], "value", "value_sets[%s].values" % i, issues)
    for node, path in _nodes(doc):
        _unique(node.get("alias_name", []), "", (path + "." if path else "") + "alias_name", issues, alias=True)


def _combinations(doc, issues):
    for i, node in enumerate(doc["object_types"]):
        for j, attr in enumerate(node["attributes"]):
            path = "object_types[%s].attributes[%s]." % (i, j)
            kind, item = attr["data_type"], attr.get("item_type")
            expected = {"item_type": kind == "array",
                        "value_set": kind == "enum" or (kind == "array" and item == "enum"),
                        "ref": kind == "object" or (kind == "array" and item == "object")}
            for field, required in expected.items():
                if required and not attr.get(field):
                    issues.append(ValidationIssue(path + field, "missing_required", "此类型必须提供 " + field))
                elif not required and attr.get(field) is not None:
                    issues.append(ValidationIssue(path + field, "invalid_field_combination", "此类型不能提供 " + field))


def _references(doc, issues):
    classes = {nfkc_casefold(node["name"]): node for node in doc["object_types"]}
    enums = {nfkc_casefold(node["name"]): node for node in doc["value_sets"]}
    attrs = {(nfkc_casefold(node["name"]), nfkc_casefold(a["name"]))
             for node in doc["object_types"] for a in node["attributes"]}
    values = {(nfkc_casefold(node["name"]), nfkc_casefold(v["value"]))
              for node in doc["value_sets"] for v in node["values"]}

    def check(found, raw, path):
        if not found:
            issues.append(ValidationIssue(path, "unresolved_reference", "引用目标不存在：%s" % raw))

    for i, node in enumerate(doc["object_types"]):
        for j, ref in enumerate(node["identity"]):
            check((nfkc_casefold(node["name"]), nfkc_casefold(ref)) in attrs, ref,
                  "object_types[%s].identity[%s]" % (i, j))
        for j, attr in enumerate(node["attributes"]):
            for field, index in (("ref", classes), ("value_set", enums)):
                ref = attr.get(field)
                if ref:
                    check(nfkc_casefold(ref) in index, ref, "object_types[%s].attributes[%s].%s" % (i, j, field))
    for i, relation in enumerate(doc["relations"]):
        for field in ("subject", "object"):
            check(nfkc_casefold(relation[field]) in classes, relation[field], "relations[%s].%s" % (i, field))
    for i, rule in enumerate(doc["rules"]):
        for j, ref in enumerate(rule["applies_to"]):
            check(nfkc_casefold(ref) in classes, ref, "rules[%s].applies_to[%s]" % (i, j))
    for i, term in enumerate(doc["terms"]):
        ref = term.get("refers_to")
        if not ref:
            continue
        folded = nfkc_casefold(ref)
        found = folded in classes or folded in enums
        if "." in ref:
            pair = tuple(nfkc_casefold(s) for s in ref.split(".", 1))
            found = found or pair in attrs or pair in values
        check(found, ref, "terms[%s].refers_to" % i)


def project_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {key: doc[key] for key in ("client", "product", "name", "alias_name", "description")}


def validate_document(raw: Any) -> ValidatedDocument:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, RecursionError):
            _fail([ValidationIssue("$", "invalid_json", "data_json 不是合法 JSON")])
    if not isinstance(raw, dict):
        _fail([ValidationIssue("$", "invalid_type", "data_json 必须是 object 或 JSON 对象字符串")])
    try:
        _check_size(document_size(raw))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _fail([ValidationIssue("$", "invalid_json", "data_json 必须只包含合法 JSON 值")])
    if "schema_version" not in raw:
        _fail([ValidationIssue("schema_version", "missing_required", "缺少 schema_version")])
    if raw["schema_version"] != SCHEMA_VERSION:
        raise OntologyError(ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED, 422, "仅支持 schema_version 1.0",
                            [{"path": "schema_version", "reason": "unsupported_schema_version", "supported": [SCHEMA_VERSION]}])
    issues = []
    try:
        _reserved(raw, issues)
        normalized = _strip(raw)
    except RecursionError:
        _fail([ValidationIssue("$", "invalid_json", "JSON 嵌套超出可处理深度")])
    reserved = bool(issues)
    try:
        model = OntologyDocument.model_validate(normalized)
    except ValidationError as exc:
        _fail(issues + pydantic_issues(exc.errors(include_url=False)), reserved)
    try:
        doc = model.model_dump(exclude_none=True)
    except (ValueError, RecursionError):
        _fail(issues + [ValidationIssue("$", "invalid_json", "JSON 嵌套超出可处理深度")], reserved)
    # Free-form dictionaries have byte limits but retain their arbitrary JSON shape.
    for node, path in _nodes(doc):
        for field in ("llm_hints", "extensions"):
            if field in node:
                limit = 64 * 1024 if not path else 16 * 1024
                if document_size(node[field]) > limit:
                    issues.append(ValidationIssue((path + "." if path else "") + field, "too_long",
                                                   "%s 序列化不能超过 %s 字节" % (field, limit)))
    if any(i.reason == "too_long" for i in issues):
        _fail(issues, reserved)
    _uniqueness(doc, issues)
    _combinations(doc, issues)
    _references(doc, issues)
    _fail(issues, reserved)
    size = document_size(doc)
    _check_size(size)  # Defaults must not expand a valid input past the storage limit.
    if size > WARN_DOCUMENT_BYTES:
        logger.warning("ontology document above recommended size: ontology_id=pending bytes=%s", size)
    return ValidatedDocument(document=doc, document_bytes=size, **project_document(doc))
