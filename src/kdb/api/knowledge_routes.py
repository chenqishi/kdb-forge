#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""knowledge modify 路由 —— POST /knowledge/modify_direct_update。

接上游（sell_agent）**已决策好的写入计划**（哪些 doc 改成什么 / 是否插一条新 QA），
忠实落到一个 es_index。**不做 LLM / 检索 / 权限**——那些都在 sell_agent 完成。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from kdb.crud.service import KnowledgeService
from kdb.modify.models import ModifyPlan
from kdb.modify.service import apply_modify_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# 共享 KnowledgeService（repo+embedding 重，按需懒构建一次；index 按请求传）
_svc: Optional[KnowledgeService] = None
_svc_lock = threading.Lock()


def _get_service() -> KnowledgeService:
    global _svc
    if _svc is None:
        with _svc_lock:
            if _svc is None:
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


class _DryService:
    """dry_run 占位：apply_modify_plan dry_run 分支不触碰任何写方法。"""
    pass
