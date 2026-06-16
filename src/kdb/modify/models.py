#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""knowledge modify —— "按已决策计划写入"的数据模型。

本模块只承载**纯数据写入计划**：上游（sell_agent）已经用 LLM 决策好「哪些 doc 改成什么内容、
是否插入一条新 QA」，这里只负责把计划落到 ES。**不含任何 LLM / 检索 / 业务权限判断。**

强约束：一个 ModifyPlan 只能写**一个** es_index（单库写入由本层兜底校验）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UpdateItem:
    """对一条已存在知识的更新：按 document_id 把 title/content 覆盖为新值。"""

    document_id: str
    new_content: str
    new_title: Optional[str] = None        # 不传则保留原 title
    old_title: Optional[str] = None         # 仅回显/审计用
    old_content: Optional[str] = None       # 仅回显/审计用


@dataclass
class InsertItem:
    """插入一条新 QA 知识（仅 allow_insert=True 时生效）。"""

    title: str
    content: str
    data_type: str = "qa"


@dataclass
class ModifyPlan:
    """一次写入计划，**只针对一个 es_index**。"""

    es_index: str
    updates: List[UpdateItem] = field(default_factory=list)
    insert: Optional[InsertItem] = None
    allow_insert: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModifyPlan":
        ups = [UpdateItem(**u) if not isinstance(u, UpdateItem) else u
               for u in (d.get("updates") or [])]
        ins = d.get("insert")
        if ins and not isinstance(ins, InsertItem):
            ins = InsertItem(**ins)
        return cls(
            es_index=d["es_index"],
            updates=ups,
            insert=ins,
            allow_insert=bool(d.get("allow_insert", False)),
        )


@dataclass
class ModifyResult:
    """写入结果（与旧 /modify_knowledge_direct_update 响应兼容的字段子集）。"""

    success: bool
    has_correction: bool
    message: str
    es_index: str
    dry_run: bool
    updated_items: List[Dict[str, Any]] = field(default_factory=list)
    inserted_item: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "has_correction": self.has_correction,
            "message": self.message,
            "es_index": self.es_index,
            "dry_run": self.dry_run,
            "updated_items": self.updated_items,
            "inserted_item": self.inserted_item,
            "errors": self.errors,
        }
