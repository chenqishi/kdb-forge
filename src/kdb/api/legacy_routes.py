"""Compatibility routes for the legacy :8003 HTTP search service.

The old service exposed eleven POST routes from one FastAPI application.  Retrieval
routes are mounted by :mod:`kdb.api.search_routes`; this module supplies the
remaining management routes while preserving the old JSON contracts.  All ES
access is lazy, so importing the application or running dry tests never contacts
Elasticsearch.
"""

from __future__ import annotations

import copy
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legacy-compat"])
_service = None  # type: ignore
_service_lock = threading.Lock()
_modifier = None  # Optional injected legacy Dify modifier for deployments/tests.


# ---------------------------------------------------------------------------
# Request/response models copied from the old service contract.
# ---------------------------------------------------------------------------
class InsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: Optional[str] = Field(None, alias="_id")
    title: Optional[str] = None
    content: Optional[str] = None
    multimodal_contents: Optional[List[Dict[str, Any]]] = None
    data_type: Optional[str] = None
    from_type: Optional[str] = None
    index_names: str
    platform: Optional[str] = None
    audit_result: Optional[int] = None
    client: Optional[str] = None
    del_flag: Optional[int] = None
    tags: Optional[List[str]] = None
    from_type_norm: Optional[str] = None
    dataset: Optional[str] = None
    task_id: Optional[str] = None
    categoryId: Optional[str] = None
    categoryName: Optional[str] = None
    category_infos: Optional[List[Dict[str, Any]]] = None
    ext_info: Optional[Dict[str, Any]] = None
    refresh_imm: bool = False
    is_need_llm: bool = False
    is_update_data: bool = True

    @property
    def _id(self) -> Optional[str]:
        """Expose the aliased ID under the old attribute name."""
        return self.id

    def get_ext_info_with_extra_fields(
        self, defined_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Collect Pydantic extra fields into ``ext_info`` as old callers expect."""
        fields = set(defined_fields or ())
        extras: Dict[str, Any] = {}
        for field_name, value in self.model_dump(exclude_none=True).items():
            if field_name in {"categoryId", "categoryName"}:
                continue
            if field_name not in fields:
                extras[field_name] = value
        merged = dict(self.ext_info or {})
        merged.update(extras)
        return merged


class InsertResponse(BaseModel):
    success: bool
    message: str = ""


class DeleteRequest(BaseModel):
    id: str = Field(..., description="数据ID")
    index_names: str = Field(..., description="索引名称")
    refresh_imm: bool = Field(False, description="是否立即刷新")


class DeleteResponse(BaseModel):
    success: bool
    message: str = ""


class ValueCollectionRequest(BaseModel):
    index_name: str
    field_name: str
    size: int = Field(10000, ge=1)
    include_doc_count: bool = False
    extra_query: Optional[Dict[str, Any]] = None


class ValueCollectionResponse(BaseModel):
    success: bool
    values: Union[List[str], List[Dict[str, Any]]] = Field(default_factory=list)
    total_count: int = 0
    message: str = ""


class ListFileNamesRequest(BaseModel):
    index_name: str
    keyword: Optional[str] = None
    size: int = Field(200, ge=1, le=1000)


class ListFileNamesResponse(BaseModel):
    success: bool
    values: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    message: str = ""


class PreviewDeleteByFileRequest(BaseModel):
    index_name: str
    file_names: List[str]
    match_mode: str = "exact"
    data_types: Optional[List[str]] = None
    audit_results: Optional[List[int]] = None
    sample_size: int = Field(10, ge=0, le=50)


class PreviewDeleteByFileResponse(BaseModel):
    success: bool
    total_count: int = 0
    by_file: List[Dict[str, Any]] = Field(default_factory=list)
    type_count: Dict[str, int] = Field(default_factory=dict)
    samples: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    message: str = ""


class DeleteByFileRequest(BaseModel):
    index_name: str
    file_names: List[str]
    match_mode: str = "exact"
    data_types: Optional[List[str]] = None
    audit_results: Optional[List[int]] = None


class DeleteByFileResponse(BaseModel):
    success: bool
    deleted_count: int = 0
    snapshot_path: Optional[str] = None
    message: str = ""


class UpdateByConditionRequest(BaseModel):
    index_name: str
    update_fields: Dict[str, Any]
    conditions: List[Dict[str, Any]]


class UpdateByConditionResponse(BaseModel):
    success: bool
    updated_count: int = 0
    message: str = ""


class ModifyKnowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    es_index: str
    new_query_info: Dict[str, Any]
    old_query_info: Dict[str, Any] = Field(default_factory=dict)
    search_querys: Optional[List[str]] = None
    write_db_id: Optional[str] = None
    allow_insert: bool = False


class ModifyKnowledgeResponse(BaseModel):
    success: bool
    has_correction: bool = False
    message: str = ""
    modify_qa_infos: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Lazy dependencies and small normalization helpers.
# ---------------------------------------------------------------------------
def _get_service():
    """Build the ES8 KnowledgeService only on the first real request."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                from kdb.crud.service import KnowledgeService

                config_path = os.environ.get(
                    "KDB_FORGE_CONFIG", "config/config_search_runtime.local.json"
                )
                _service = KnowledgeService.from_config(config_path)
                logger.info("legacy compatibility service initialized from %s", config_path)
    return _service


def _get_modifier():
    """Return an optional injected old Dify modifier.

    The rebuild intentionally does not construct Dify clients from HTTP requests.
    Deployments that still provide this feature can inject an object exposing
    ``modify_knowledge`` and ``modify_knowledge_direct_update``.
    """
    return _modifier


def _category_infos(request: InsertRequest) -> Optional[List[Dict[str, Any]]]:
    """Convert the old comma-separated category fields into explicit entries."""
    if request.category_infos:
        return [dict(item) for item in request.category_infos]
    if request.categoryId and request.categoryName:
        category_ids = request.categoryId.split(",")
        category_names = request.categoryName.split(",")
        if len(category_ids) != len(category_names):
            raise HTTPException(status_code=400, detail="categoryId和categoryName数量不一致")
        return [
            {
                "category_id": str(category_id),
                "category_name": category_name,
                "score": 1.0,
                "source": "manual",
            }
            for category_id, category_name in zip(category_ids, category_names)
        ]
    return None


def _insert_document(request: InsertRequest) -> Dict[str, Any]:
    """Build the old document dict, retaining extension fields for Service."""
    raw = request.model_dump(by_alias=True, exclude_none=True)
    for key in ("index_names", "refresh_imm", "is_need_llm", "is_update_data", "categoryId", "categoryName"):
        raw.pop(key, None)
    categories = _category_infos(request)
    if categories is not None:
        raw["category_infos"] = categories
    # Pydantic extras are intentionally carried through.  KnowledgeService moves
    # unknown schema keys into ext_info just like the old process_one_data path.
    return raw


def _unsupported_modifier_message() -> str:
    return (
        "旧 modify_knowledge 路径需要 Dify recall/modify 模型；"
        "当前 ES8 CRUD 进程未配置该外部依赖"
    )


# ---------------------------------------------------------------------------
# Legacy routes (the search/web_search routes are in search_routes.py).
# ---------------------------------------------------------------------------
@router.post("/insert", response_model=InsertResponse)
def insert(request: InsertRequest) -> InsertResponse:
    """旧 ``POST /insert``，透传至 ``KnowledgeService.insert_data``。"""
    if not request.index_names:
        raise HTTPException(status_code=400, detail="index_names不能为空")
    try:
        service = _get_service()
        document = _insert_document(request)
        data_type = request.data_type or (None if request.id else "qa")
        from_type = request.from_type or (None if request.id else "chat")
        if data_type is not None:
            document["data_type"] = data_type
        if from_type is not None:
            document["from_type"] = from_type
        ok, message = service.insert_data(
            document,
            index_name=request.index_names,
            check_duplicate=True,
            is_update_data=request.is_update_data,
            refresh_imm=request.refresh_imm,
            is_need_llm=request.is_need_llm,
        )
        return InsertResponse(
            success=bool(ok),
            message=f"数据已插入: {request.title}" if ok else str(message),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("legacy /insert failed")
        return InsertResponse(success=False, message=f"插入失败: {exc}")


@router.post("/delete", response_model=DeleteResponse)
def delete(request: DeleteRequest) -> DeleteResponse:
    """旧 ``POST /delete``，按 ID 硬删除。"""
    try:
        ok = _get_service().delete_data(
            data_id=request.id,
            index_names=request.index_names,
            refresh=request.refresh_imm,
        )
        return DeleteResponse(
            success=bool(ok),
            message=f"数据{'删除成功' if ok else '删除失败'}: {request.id}",
        )
    except Exception as exc:
        logger.exception("legacy /delete failed")
        return DeleteResponse(success=False, message=f"删除失败: {exc}")


@router.post("/get_value_collection", response_model=ValueCollectionResponse)
@router.post("/get_unique_values", response_model=ValueCollectionResponse)
def get_value_collection(request: ValueCollectionRequest) -> ValueCollectionResponse:
    """Return terms values with the old value/count response shape."""
    if not request.index_name:
        raise HTTPException(status_code=400, detail="index_name不能为空")
    if not request.field_name:
        raise HTTPException(status_code=400, detail="field_name不能为空")
    try:
        values = _get_service().get_unique_values(
            index_name=request.index_name,
            field_name=request.field_name,
            size=request.size,
            include_doc_count=request.include_doc_count,
            extra_query=request.extra_query,
        )
        values = values or []
        return ValueCollectionResponse(
            success=True,
            values=values,
            total_count=len(values),
            message=f"成功获取字段 {request.field_name} 的值集合，共 {len(values)} 个值",
        )
    except Exception as exc:
        logger.exception("legacy /get_value_collection failed")
        return ValueCollectionResponse(success=False, message=f"获取值集合失败: {exc}")


@router.post("/list_file_names", response_model=ListFileNamesResponse)
def list_file_names(request: ListFileNamesRequest) -> ListFileNamesResponse:
    """List source file names in the old scoped response."""
    try:
        values = _get_service().list_file_names(
            index_name=request.index_name, keyword=request.keyword, size=request.size
        )
        return ListFileNamesResponse(
            success=True,
            values=values,
            total_count=len(values),
            message=f"共 {len(values)} 个来源文件（仅统计 document/html/manual 来源）",
        )
    except Exception as exc:
        logger.exception("legacy /list_file_names failed")
        return ListFileNamesResponse(success=False, message=f"获取文件名列表失败: {exc}")


@router.post("/preview_delete_by_file", response_model=PreviewDeleteByFileResponse)
def preview_delete_by_file(request: PreviewDeleteByFileRequest) -> PreviewDeleteByFileResponse:
    """Preview file soft deletion; this endpoint never writes ES."""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        result = _get_service().preview_delete_by_file(
            index_name=request.index_name,
            file_names=request.file_names,
            match_mode=request.match_mode,
            data_types=request.data_types,
            audit_results=request.audit_results,
            sample_size=request.sample_size,
        )
        return PreviewDeleteByFileResponse(
            success=True,
            total_count=result.get("total_count", 0),
            by_file=result.get("by_file", []),
            type_count=result.get("type_count", {}),
            samples=result.get("samples", []),
            warnings=result.get("warnings", []),
            message=f"预计软删除 {result.get('total_count', 0)} 条，确认后用相同参数调用 /delete_by_file",
        )
    except Exception as exc:
        logger.exception("legacy /preview_delete_by_file failed")
        return PreviewDeleteByFileResponse(success=False, message=f"预览失败: {exc}")


@router.post("/delete_by_file", response_model=DeleteByFileResponse)
def delete_by_file(request: DeleteByFileRequest) -> DeleteByFileResponse:
    """Soft-delete source files after the compatibility layer writes a snapshot."""
    if not request.file_names:
        raise HTTPException(status_code=400, detail="file_names 不能为空")
    if request.match_mode not in ("exact", "fuzzy"):
        raise HTTPException(status_code=400, detail="match_mode 只能是 exact 或 fuzzy")
    try:
        result = _get_service().delete_by_file(
            index_name=request.index_name,
            file_names=request.file_names,
            match_mode=request.match_mode,
            data_types=request.data_types,
            audit_results=request.audit_results,
        )
        return DeleteByFileResponse(**result)
    except Exception as exc:
        logger.exception("legacy /delete_by_file failed")
        return DeleteByFileResponse(success=False, message=f"删除失败: {exc}")


@router.post("/update_by_condition", response_model=UpdateByConditionResponse)
def update_by_condition(request: UpdateByConditionRequest) -> UpdateByConditionResponse:
    """Run the old AND-condition update operation through ES8 update-by-query."""
    if not request.index_name:
        raise HTTPException(status_code=400, detail="index_name不能为空")
    if not request.update_fields:
        raise HTTPException(status_code=400, detail="update_fields不能为空")
    if not request.conditions:
        raise HTTPException(status_code=400, detail="conditions不能为空")
    try:
        ok = _get_service().update_data_value(
            index_name=request.index_name,
            update_value_dict=request.update_fields,
            conditions=request.conditions,
        )
        # The old implementation did not expose the provider's update count.
        return UpdateByConditionResponse(
            success=bool(ok), updated_count=0,
            message="条件更新操作完成" if ok else "条件更新失败",
        )
    except Exception as exc:
        logger.exception("legacy /update_by_condition failed")
        return UpdateByConditionResponse(success=False, message=f"条件更新失败: {exc}")


def _call_modifier(method_name: str, request: ModifyKnowledgeRequest) -> Any:
    """Call an injected old modifier, keeping its positional contract stable."""
    modifier = _get_modifier()
    if modifier is None:
        raise RuntimeError(_unsupported_modifier_message())
    method = getattr(modifier, method_name)
    if method_name == "modify_knowledge":
        return method(
            es_index=request.es_index,
            new_query_info=copy.deepcopy(request.new_query_info),
            old_query_info=copy.deepcopy(request.old_query_info),
            search_querys=copy.deepcopy(request.search_querys),
            write_db_id=request.write_db_id,
        )
    return method(
        es_index=request.es_index,
        new_query_info=copy.deepcopy(request.new_query_info),
        old_query_info=copy.deepcopy(request.old_query_info),
        search_querys=copy.deepcopy(request.search_querys),
        allow_insert=request.allow_insert,
    )


@router.post("/modify_knowledge_direct_update", response_model=ModifyKnowledgeResponse)
def modify_knowledge_direct_update(request: ModifyKnowledgeRequest) -> ModifyKnowledgeResponse:
    """Preserve the old Dify-backed direct-modify route when a modifier is injected."""
    if not request.es_index:
        raise HTTPException(status_code=400, detail="es_index不能为空")
    if not request.new_query_info:
        raise HTTPException(status_code=400, detail="new_query_info不能为空")
    try:
        message, has_correction = _call_modifier("modify_knowledge_direct_update", request)
        return ModifyKnowledgeResponse(
            success=True, message=message or "知识修改完成", has_correction=bool(has_correction)
        )
    except Exception as exc:
        logger.warning("legacy direct modify unavailable/failed: %s", exc)
        return ModifyKnowledgeResponse(success=False, message=f"知识直接更新失败: {exc}")


@router.post("/modify_knowledge", response_model=ModifyKnowledgeResponse)
def modify_knowledge(request: ModifyKnowledgeRequest) -> ModifyKnowledgeResponse:
    """Preserve the old LLM-assisted modify route when a modifier is injected."""
    if not request.es_index:
        raise HTTPException(status_code=400, detail="es_index不能为空")
    if not request.new_query_info:
        raise HTTPException(status_code=400, detail="new_query_info不能为空")
    if not request.old_query_info:
        raise HTTPException(status_code=400, detail="old_query_info不能为空")
    try:
        infos = _call_modifier("modify_knowledge", request)
        return ModifyKnowledgeResponse(
            success=True,
            message=f"成功处理 {len(infos) if infos else 0} 条知识",
            modify_qa_infos=infos,
        )
    except Exception as exc:
        logger.warning("legacy modify unavailable/failed: %s", exc)
        return ModifyKnowledgeResponse(success=False, message=f"知识修改失败: {exc}")


__all__ = [
    "router", "InsertRequest", "InsertResponse", "DeleteRequest", "DeleteResponse",
    "ValueCollectionRequest", "ValueCollectionResponse", "ListFileNamesRequest",
    "ListFileNamesResponse", "PreviewDeleteByFileRequest", "PreviewDeleteByFileResponse",
    "DeleteByFileRequest", "DeleteByFileResponse", "UpdateByConditionRequest",
    "UpdateByConditionResponse", "ModifyKnowledgeRequest", "ModifyKnowledgeResponse",
]
