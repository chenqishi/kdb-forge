#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""knowledge modify service —— 把 ModifyPlan 落到一个 ES index。

职责（**纯写入，零 LLM / 零检索 / 零权限**）：
- 按 document_id 局部更新 title/content（重算向量、刷新 update_time）。
- 可选插入一条新 QA（仅 allow_insert=True 且 plan.insert 非空）。
- **单库**：plan 只带一个 es_index，所有写入都打到它。
- dry_run=True：不真写，只回计划。

权限/确认/选库/抽取/精排/改写都在上游 sell_agent 完成，本层只忠实执行。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from kdb.modify.models import ModifyPlan, ModifyResult

if TYPE_CHECKING:  # 仅类型注解用；运行期不导入 kdb.crud(避免拉入旧 ES 依赖，单测可纯 mock)
    from kdb.crud.service import KnowledgeService

logger = logging.getLogger(__name__)


def apply_modify_plan(
    knowledge_service: KnowledgeService,
    plan: ModifyPlan,
    dry_run: bool = False,
) -> ModifyResult:
    """执行一次写入计划，返回 ModifyResult。

    Args:
        knowledge_service: kdb.crud.KnowledgeService（共享 repo+embedding；index 按 plan.es_index 传）。
        plan: 写入计划（单 es_index）。
        dry_run: True 则不真写，仅回计划。
    """
    es_index = (plan.es_index or "").strip()
    if not es_index:
        return ModifyResult(success=False, has_correction=False,
                            message="es_index 为空，拒绝写入", es_index="",
                            dry_run=dry_run, errors=["empty_es_index"])

    has_correction = bool(plan.updates) or bool(plan.insert and plan.allow_insert)
    updated_items: list = []
    inserted_item: Optional[dict] = None
    errors: list = []

    # dry_run：只回计划，不写
    if dry_run:
        for u in plan.updates:
            updated_items.append({"document_id": u.document_id, "old_title": u.old_title,
                                  "old_content": u.old_content, "new_title": u.new_title,
                                  "new_content": u.new_content, "applied": False})
        if plan.insert and plan.allow_insert:
            inserted_item = {"title": plan.insert.title, "content": plan.insert.content,
                             "data_type": plan.insert.data_type, "applied": False}
        return ModifyResult(success=True, has_correction=has_correction,
                            message="[dry_run] 计划已生成，未写入", es_index=es_index,
                            dry_run=True, updated_items=updated_items, inserted_item=inserted_item)

    # 实写：逐条 update（按 _id，重算向量，立即刷新可见）
    for u in plan.updates:
        try:
            doc: dict[str, Any] = {"content": u.new_content}
            if u.new_title is not None:
                doc["title"] = u.new_title
            ok = knowledge_service.update(
                u.document_id, doc, index_name=es_index,
                regenerate_embedding=True, refresh=True,
            )
            updated_items.append({"document_id": u.document_id, "old_title": u.old_title,
                                  "old_content": u.old_content, "new_title": u.new_title,
                                  "new_content": u.new_content, "applied": bool(ok)})
            if not ok:
                errors.append(f"update_failed:{u.document_id}")
        except Exception as exc:  # pragma: no cover - 真实 ES 异常
            logger.exception("apply_modify_plan update 异常 doc_id=%s", u.document_id)
            errors.append(f"update_error:{u.document_id}:{exc}")
            updated_items.append({"document_id": u.document_id, "applied": False, "error": str(exc)})

    # 可选 insert（仅 allow_insert）
    if plan.insert and plan.allow_insert:
        try:
            new_doc = {"title": plan.insert.title, "content": plan.insert.content,
                       "data_type": plan.insert.data_type}
            ok, msg = knowledge_service.insert_text(new_doc, index_name=es_index, refresh_imm=True)
            inserted_item = {"title": plan.insert.title, "content": plan.insert.content,
                             "data_type": plan.insert.data_type, "applied": bool(ok), "message": msg}
            if not ok:
                errors.append(f"insert_failed:{msg}")
        except Exception as exc:  # pragma: no cover
            logger.exception("apply_modify_plan insert 异常")
            errors.append(f"insert_error:{exc}")

    applied_any = any(it.get("applied") for it in updated_items) or bool(
        inserted_item and inserted_item.get("applied"))
    success = applied_any and not errors if has_correction else True
    msg = ("写入完成" if applied_any else "无成功写入") if has_correction else "无可写入项"
    return ModifyResult(success=bool(success), has_correction=has_correction, message=msg,
                        es_index=es_index, dry_run=False, updated_items=updated_items,
                        inserted_item=inserted_item, errors=errors)
