"""Seven complete-document use cases; no dependency on HTTP request models."""
import logging
from typing import Any, Optional

from .errors import (OntologyError, ONTOLOGY_BAD_REQUEST, ONTOLOGY_NOT_FOUND,
                     ONTOLOGY_REVISION_CONFLICT, ONTOLOGY_SCOPE_IMMUTABLE)
from .repository import OntologyRepository
from .schema import (DEFAULT_PAGE_SIZE, DEFAULT_REVIEW_STATUS, DEFAULT_STATUS, MAX_PAGE_SIZE,
                     REVIEW_STATUS_VALUES, STATUS_VALUES, WARN_DOCUMENT_BYTES)
from .validation import document_size, validate_document

logger = logging.getLogger(__name__)
META_FIELDS = ("ontology_id", "client", "product", "name", "status", "review_status", "revision", "create_time", "update_time")
LIST_FIELDS = META_FIELDS + ("alias_name", "description")
OUTLINE_FIELDS = ("ontology_id", "client", "product", "name", "status", "review_status", "revision", "update_time")


def _value(body, name, default=None):
    return body.get(name, default) if isinstance(body, dict) else getattr(body, name, default)


def _status(value, field="status", location="body", allow_all=False):
    values = REVIEW_STATUS_VALUES if field == "review_status" else STATUS_VALUES
    if allow_all:
        values += ("all",)
    if value not in values:
        raise OntologyError(ONTOLOGY_BAD_REQUEST, 400, "%s 必须是 %s" % (field, "、".join(values)),
                            [{"path": location + "." + field, "reason": "invalid_enum_value", "message": "非法状态"}])
    return value


def _meta(row):
    result = {key: getattr(row, key) for key in META_FIELDS}
    result["document_bytes"] = document_size(row.data_json)
    return result


def _full(row):
    result = _meta(row)
    result.update(alias_name=row.alias_name, description=row.description, del_flag=row.del_flag, data_json=row.data_json)
    return result


def _outline(row):
    doc = row.data_json
    result = {key: getattr(row, key) for key in OUTLINE_FIELDS}
    result["outline"] = {
        "object_types": [{"name": node["name"], "description": node.get("description", ""),
                          "attribute_count": len(node["attributes"]),
                          "attribute_names": [attr["name"] for attr in node["attributes"]]} for node in doc["object_types"]],
        "counts": {**{key: len(doc.get(key, [])) for key in ("object_types", "relations", "value_sets", "rules", "terms")},
                   "attributes": sum(len(node["attributes"]) for node in doc["object_types"])},
    }
    return result


def describe_scope(row, req_client, req_product):
    if row is None:
        return "none", True
    if not row.client and not row.product:
        scope = "global"
    elif not row.client:
        scope = "industry"
    elif not row.product:
        scope = "client"
    else:
        scope = "client_product"
    return scope, not (row.client == req_client and row.product == req_product)


def _warn_size(ontology_id, size):
    if size > WARN_DOCUMENT_BYTES:
        logger.warning("ontology document above recommended size: ontology_id=%s bytes=%s", ontology_id, size)


class OntologyService:
    def __init__(self, repo: OntologyRepository):
        self.repo = repo

    def _existing(self, ontology_id, include_deleted=False):
        row = self.repo.select_ontology_by_id(ontology_id)
        if row is None or (row.del_flag and not include_deleted):
            raise OntologyError(ONTOLOGY_NOT_FOUND, 404, "本体不存在或已删除")
        return row

    def insert_ontology(self, body: Any) -> dict:
        status = _status(_value(body, "status") if _value(body, "status") is not None else DEFAULT_STATUS)
        review_status = _status(_value(body, "review_status") if _value(body, "review_status") is not None
                                else DEFAULT_REVIEW_STATUS, "review_status")
        vd = validate_document(_value(body, "data_json"))
        ontology_id = self.repo.insert_ontology(vd, status, review_status)
        _warn_size(ontology_id, vd.document_bytes)
        return {"success": True, "message": "", "ontology": _meta(self._existing(ontology_id))}

    def update_ontology(self, ontology_id: str, body: Any) -> dict:
        existing = self._existing(ontology_id)
        vd = validate_document(_value(body, "data_json"))
        if (vd.client, vd.product) != (existing.client, existing.product):
            raise OntologyError(ONTOLOGY_SCOPE_IMMUTABLE, 409, "作用域不可修改，请新建本体",
                                [{"current": {"client": existing.client, "product": existing.product},
                                  "requested": {"client": vd.client, "product": vd.product}}])
        status = _status(_value(body, "status") if _value(body, "status") is not None else existing.status)
        review_status = _status(_value(body, "review_status") if _value(body, "review_status") is not None
                                else DEFAULT_REVIEW_STATUS, "review_status")
        if not self.repo.update_ontology_document(ontology_id, _value(body, "revision"), vd, status, review_status):
            self._raise_write_conflict(ontology_id)
        _warn_size(ontology_id, vd.document_bytes)
        return {"success": True, "message": "", "ontology": _meta(self._existing(ontology_id))}

    def update_ontology_status(self, ontology_id: str, body: Any) -> dict:
        status, review_status = _value(body, "status"), _value(body, "review_status")
        if status is None and review_status is None:
            raise OntologyError(ONTOLOGY_BAD_REQUEST, 400, "至少提供 status 或 review_status",
                                [{"path": "body", "reason": "missing_status", "message": "状态更新不能为空"}])
        if status is not None:
            _status(status)
        if review_status is not None:
            _status(review_status, "review_status")
        if not self.repo.update_ontology_status(ontology_id, _value(body, "revision"), status, review_status):
            self._raise_write_conflict(ontology_id)
        return {"success": True, "message": "", "ontology": _meta(self._existing(ontology_id))}

    def delete_ontology(self, ontology_id: str, revision: Optional[int] = None) -> dict:
        count = self.repo.delete_ontology(ontology_id, revision)
        row = self.repo.select_ontology_by_id(ontology_id)
        if row is None:
            raise OntologyError(ONTOLOGY_NOT_FOUND, 404, "本体不存在或已删除")
        if not row.del_flag:
            self._raise_write_conflict(ontology_id)
        meta = _meta(row)
        meta["del_flag"] = 1
        return {"success": True, "message": "" if count else "本体已删除", "deleted": True, "ontology": meta}

    def get_ontology(self, ontology_id: str, view: str = "full", include_deleted: bool = False,
                     review_status: str = "approved") -> dict:
        if view not in ("full", "document", "outline"):
            raise OntologyError(ONTOLOGY_BAD_REQUEST, 400, "view 必须是 full、document 或 outline")
        _status(review_status, "review_status", "query", allow_all=True)
        row = self._existing(ontology_id, include_deleted)
        if review_status != "all" and row.review_status != review_status:
            raise OntologyError(ONTOLOGY_NOT_FOUND, 404, "未找到符合审核状态的本体")
        if view == "document":
            return {"success": True, "message": "", "ontology_id": row.ontology_id,
                    "status": row.status, "review_status": row.review_status,
                    "revision": row.revision, "document": row.data_json}
        return {"success": True, "message": "", "ontology": _full(row) if view == "full" else _outline(row)}

    def list_ontologies(self, client=None, product=None, status=None, q=None, deep=False,
             include_deleted=False, page=1, page_size=DEFAULT_PAGE_SIZE, review_status="approved") -> dict:
        if status is not None:
            _status(status, location="query")
        _status(review_status, "review_status", "query", allow_all=True)
        issues = []
        if type(page) is not int or page < 1:
            issues.append({"path": "query.page", "reason": "invalid_pagination", "message": "page 必须为正整数"})
        if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
            issues.append({"path": "query.page_size", "reason": "invalid_pagination",
                           "message": "page_size 必须为 1 至 %s 的整数" % MAX_PAGE_SIZE})
        if issues:
            raise OntologyError(ONTOLOGY_BAD_REQUEST, 400, "请求参数不合法", issues)
        rows, total = self.repo.list_ontologies(client=client, product=product, status=status, q=q, deep=deep,
                                    include_deleted=include_deleted, limit=page_size, offset=(page - 1) * page_size,
                                    review_status=None if review_status == "all" else review_status)
        return {"success": True, "message": "", "total": total, "page": page, "page_size": page_size,
                "items": [{key: getattr(row, key) for key in LIST_FIELDS} for row in rows]}

    def select_ontology(self, client: str = "", product: str = "", name: Optional[str] = None,
                include_document: bool = True) -> dict:
        row = self.repo.select_ontology(client, product, name or None)
        scope, fallback = describe_scope(row, client, product)
        ontology = None
        if row is not None:
            ontology = _outline(row)
            if include_document:
                ontology.pop("outline")
                ontology["data_json"] = row.data_json
        return {"success": True, "message": "" if row else "未找到匹配作用域的本体", "scope": scope,
                "fallback": fallback, "request": {"client": client, "product": product}, "ontology": ontology}

    def _raise_write_conflict(self, ontology_id: str) -> None:
        row = self.repo.select_ontology_by_id(ontology_id)
        if row is None or row.del_flag:
            raise OntologyError(ONTOLOGY_NOT_FOUND, 404, "本体不存在或已删除")
        raise OntologyError(ONTOLOGY_REVISION_CONFLICT, 409, "revision 不一致，请重新读取当前版本",
                            [{"current_revision": row.revision}])
