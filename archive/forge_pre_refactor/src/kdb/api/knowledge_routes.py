#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""knowledge 写入路由 —— POST /knowledge/modify_direct_update | /knowledge/insert | /knowledge/delete。

modify_direct_update：接上游（sell_agent）**已决策好的写入计划**（哪些 doc 改成什么 /
是否插一条新 QA），忠实落到一个 es_index。**不做 LLM / 检索 / 权限**——那些都在 sell_agent 完成。
insert / delete：单文档 upsert（支持 `synonyms_title` list → 单 doc + indexes 同义向量）
与按 `_id` 删除；给灌库/迁移脚本用（旧 :8003/insert 会静默丢弃 synonyms_title）。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kdb.modify.models import ModifyPlan
from kdb.modify.service import apply_modify_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# 共享 KnowledgeService（repo+embedding 重，按需懒构建一次；index 按请求传）。
# 注意：**不在模块顶层 import KnowledgeService**——它会经 legacy_bridge 拉旧 ES 依赖，
# 导致无 ES 环境(CI/纯 dry_run)连 `import kdb.api.app` 都失败。真实写入(非 dry_run)时才懒构建。
_svc = None  # type: ignore
_svc_lock = threading.Lock()


def _get_service():
    global _svc
    if _svc is None:
        with _svc_lock:
            if _svc is None:
                from kdb.crud.service import KnowledgeService  # 懒导入：仅真实写入路径触发
                cfg_path = os.environ.get("KDB_FORGE_CONFIG") or "config/config_test.json"
                _svc = KnowledgeService.from_config(cfg_path)
                logger.info("KnowledgeService 构建完成 config=%s", cfg_path)
    return _svc


class _UpdateItem(BaseModel):
    document_id: str
    new_content: str
    new_title: Optional[str] = None
    old_title: Optional[str] = None
    old_content: Optional[str] = None


class _InsertItem(BaseModel):
    title: str
    content: str
    data_type: str = "qa"


class ModifyDirectUpdateRequest(BaseModel):
    es_index: str = Field(..., description="目标库（单库，必填）")
    updates: List[_UpdateItem] = Field(default_factory=list)
    insert: Optional[_InsertItem] = None
    allow_insert: bool = False
    dry_run: bool = False


@router.post("/modify_direct_update")
def modify_direct_update(req: ModifyDirectUpdateRequest) -> Dict[str, Any]:
    """按计划写入一个 es_index。dry_run=True 只回计划不写。"""
    plan = ModifyPlan.from_dict(req.model_dump())
    if req.dry_run:
        result = apply_modify_plan(_DryService(), plan, dry_run=True)  # 无需真服务
    else:
        result = apply_modify_plan(_get_service(), plan, dry_run=False)
    return result.to_dict()


class InsertDocRequest(BaseModel):
    """单文档 upsert 请求。

    doc 为完整文档 dict（可含 `_id`/`title`/`synonyms_title`(list)/`content`/`data_type`/
    `from_type`/`audit_result`/... ），字段语义与 `KnowledgeService.insert_data` 入参一致：
    `synonyms_title` 列表会被 `_prepare_document` 展开进 `indexes`（逐条向量化），
    **单文档存储**，不会拆成多条 doc——这是与旧 :8003/insert 的关键差异（旧路由把
    `synonyms_title` 静默丢弃，见 function_schema/knowledge_routes.insert_doc.md）。
    """

    es_index: str = Field(..., description="目标库（单库，必填）")
    doc: Dict[str, Any] = Field(..., description="完整文档 dict，支持 synonyms_title(list)")
    check_duplicate: Optional[bool] = Field(
        None, description="None=取服务配置缺省；False=跳过查重（固定 _id 幂等灌库场景）"
    )
    is_update_data: bool = Field(False, description="查重命中时软删旧数据后覆盖插入")
    refresh_imm: bool = Field(False, description="写后立即刷新索引（读己之写场景）")


@router.post("/insert")
def insert_doc(req: InsertDocRequest) -> Dict[str, Any]:
    """单文档 upsert（含 synonyms_title 列表 → 单 doc + indexes 同义向量）。"""
    try:
        ok, msg = _get_service().insert_data(
            req.doc,
            check_duplicate=req.check_duplicate,
            index_name=req.es_index,
            is_update_data=req.is_update_data,
            refresh_imm=req.refresh_imm,
        )
        return {"success": bool(ok), "message": msg,
                "document_id": req.doc.get("_id"), "es_index": req.es_index}
    except Exception as exc:  # noqa: BLE001
        logger.exception("insert_doc 失败 es_index=%s _id=%s", req.es_index, req.doc.get("_id"))
        return {"success": False, "message": f"insert failed: {exc}",
                "document_id": req.doc.get("_id"), "es_index": req.es_index}


class DeleteDocRequest(BaseModel):
    es_index: str = Field(..., description="目标库（单库，必填）")
    document_id: str = Field(..., description="要删除的文档 _id")
    refresh: bool = Field(False, description="删除后立即刷新索引")


@router.post("/delete")
def delete_doc(req: DeleteDocRequest) -> Dict[str, Any]:
    """按 _id 删除一条文档。"""
    try:
        ok = _get_service().delete(req.document_id, index_name=req.es_index, refresh=req.refresh)
        return {"success": bool(ok), "document_id": req.document_id, "es_index": req.es_index}
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_doc 失败 es_index=%s _id=%s", req.es_index, req.document_id)
        return {"success": False, "message": f"delete failed: {exc}",
                "document_id": req.document_id, "es_index": req.es_index}


class _DryService:
    """dry_run 占位：apply_modify_plan dry_run 分支不触碰任何写方法。"""
    pass
