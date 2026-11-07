#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
通用业务上下文构建与缓存。

把以下来源合并为给 LLM 的“业务背景 + 抽取方向”，供 QA / Segment 生成使用：
  1. 前端/任务传入的 business_context_text（最高优先级、成本最低）；
  2. data_chat_history 提炼的真实用户 query / 高频意图（仅校准抽取方向）；
  3.（可选）网络业务背景（默认关闭，仅 enable_web_context=true 时）。

按 client + knowledge_objective + 来源 hash 缓存，避免每次任务重复构建。
所有子来源均“可选 + 优雅降级”，任一来源不可用都不影响主流程。

兼容要求：
- enable_context_enrichment=false 时，返回 enabled=False 的最小结构，调用方据此不改 prompt。
"""

import hashlib
import json
import logging
import os
import time
from typing import Optional

# 默认保留/拒绝边界（通用，不绑定具体客户）
DEFAULT_KEEP = ["操作步骤", "条件限制", "费用费率", "时间地点报名方式", "适用对象", "平台规则"]
DEFAULT_REJECT = ["品牌宣传", "版权隐私", "关注公众号", "无事实广告", "免责声明"]


def _context_hash(client: str, knowledge_objective: Optional[str],
                  business_context_text: Optional[str],
                  enable_chat_query_context: bool, enable_web_context: bool) -> str:
    raw = "||".join([
        client or "",
        knowledge_objective or "",
        business_context_text or "",
        f"chat={enable_chat_query_context}",
        f"web={enable_web_context}",
    ]).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _render_context_text(client, knowledge_objective, business_context_text,
                         query_intents, web_text) -> str:
    """把各来源拼成最终给 LLM 的业务背景文本。"""
    parts = [f"客户：{client}"]
    if knowledge_objective:
        parts.append(f"知识目标：{knowledge_objective}")
    if business_context_text:
        parts.append(f"业务背景：{business_context_text}")
    if query_intents:
        lines = ["用户高频问题意图（仅用于校准抽取方向，不要直接当作知识答案）："]
        for it in query_intents[:30]:
            intent = it.get("intent", "")
            samples = "；".join(it.get("sample_queries", [])[:2])
            lines.append(f"- {intent}" + (f"（如：{samples}）" if samples else ""))
        parts.append("\n".join(lines))
    if web_text:
        parts.append(
            "网络业务背景（仅用于理解客户业务画像/术语，禁止作为当前文档事实写入答案）：\n"
            + web_text
        )
    return "\n\n".join(parts).strip()


def build_business_context(
    *,
    client: str,
    knowledge_objective: Optional[str],
    business_context_text: Optional[str],
    enable_context_enrichment: bool,
    enable_chat_query_context: bool,
    enable_web_context: bool,
    cache_dir: str,
    ttl_days: int = 30,
    task_info: Optional[dict] = None,
    now_ts: Optional[float] = None,
) -> dict:
    """构建（并缓存）业务上下文。

    Args:
        client: 客户名。
        knowledge_objective: 本次知识目标。
        business_context_text: 前端/任务传入的业务背景文本。
        enable_context_enrichment: 总开关；False 时返回 enabled=False 最小结构。
        enable_chat_query_context: 是否从 data_chat_history 提炼用户意图。
        enable_web_context: 是否启用网络业务背景（默认应为 False）。
        cache_dir: 缓存目录。
        ttl_days: 缓存有效期天数。
        task_info: 原始 task 字段，用于读取 llm_model_name/llm_provider 等。
        now_ts: 时间戳注入（测试用）。

    Returns:
        业务上下文 dict。
    """
    task_info = task_info or {}
    now_ts = now_ts if now_ts is not None else time.time()

    query_exclude_terms = task_info.get("chat_query_exclude_terms", [])
    if isinstance(query_exclude_terms, str):
        query_exclude_terms = [
            term.strip() for term in query_exclude_terms.split(",") if term.strip()
        ]
    elif isinstance(query_exclude_terms, (list, tuple, set)):
        query_exclude_terms = [
            str(term).strip() for term in query_exclude_terms if str(term).strip()
        ]
    else:
        query_exclude_terms = []

    if not enable_context_enrichment:
        return {
            "enabled": False,
            "client": client,
            "context_text": "",
            "query_intents": [],
            "business_boundaries": {"keep": [], "reject": []},
            "sources": {
                "frontend_context": False,
                "chat_history": False,
                "existing_knowledge": False,
                "web_search": False,
            },
            "cache_hit": False,
            "cache_path": "",
        }

    os.makedirs(cache_dir, exist_ok=True)
    cache_context_text = "||".join([
        business_context_text or "",
        "query_exclude=" + json.dumps(
            sorted(set(query_exclude_terms)), ensure_ascii=False
        ),
    ])
    key = _context_hash(client, knowledge_objective, cache_context_text,
                        enable_chat_query_context, enable_web_context)
    cache_path = os.path.join(cache_dir, f"ctx_{key}.json")

    # 命中有效缓存
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if now_ts - cached.get("generated_at_ts", 0) < ttl_days * 86400:
                cached["cache_hit"] = True
                cached["cache_path"] = cache_path
                logging.info(f"business_context_builder: 命中缓存 {cache_path}")
                return cached
        except Exception as exc:
            logging.warning(f"business_context_builder: 读取缓存失败，忽略重建: {exc}")

    model_name = task_info.get("llm_model_name")
    provider = task_info.get("llm_provider")

    sources = {
        "frontend_context": bool(business_context_text),
        "chat_history": False,
        "existing_knowledge": False,
        "web_search": False,
    }

    # 2. data_chat_history 用户意图（可选）
    query_intents = []
    if enable_chat_query_context:
        try:
            from kdb.mining.generation.processing.chat_query_context import (
                load_client_queries, summarize_query_intents,
            )
            queries = load_client_queries(
                client=client,
                admin_user_id=task_info.get("admin_user_id"),
                app_id=task_info.get("app_id"),
                days=int(task_info.get("chat_history_days", 180)),
            )
            if queries and query_exclude_terms:
                lowered_terms = [term.lower() for term in query_exclude_terms]
                before_count = len(queries)
                queries = [
                    query for query in queries
                    if not any(term in query.lower() for term in lowered_terms)
                ]
                logging.info(
                    "business_context_builder: chat query 串站过滤 "
                    f"{before_count}->{len(queries)}, terms={query_exclude_terms}"
                )
            if queries:
                query_intents = summarize_query_intents(
                    queries, client=client, model_name=model_name, provider=provider,
                )
                sources["chat_history"] = bool(query_intents)
        except Exception as exc:
            logging.warning(f"business_context_builder: chat 意图构建失败，降级跳过: {exc}")

    # 3. 网络业务背景（默认关闭）
    web_text = ""
    if enable_web_context:
        try:
            from kdb.mining.generation.processing.web_business_context import build_web_business_context
            web_result = build_web_business_context(
                client=client,
                knowledge_objective=knowledge_objective,
                cache_dir=os.path.join(cache_dir, "web"),
                ttl_days=int(task_info.get("context_cache_ttl_days", ttl_days)),
                now_ts=now_ts,
            )
            web_text = web_result.get("context_text", "")
            sources["web_search"] = bool(web_text)
        except Exception as exc:
            logging.warning(f"business_context_builder: 网络背景构建失败，降级跳过: {exc}")

    context_text = _render_context_text(
        client, knowledge_objective, business_context_text, query_intents, web_text,
    )

    result = {
        "enabled": True,
        "client": client,
        "knowledge_objective": knowledge_objective or "",
        "context_text": context_text,
        "query_intents": query_intents,
        "business_boundaries": {"keep": DEFAULT_KEEP, "reject": DEFAULT_REJECT},
        "sources": sources,
        "cache_hit": False,
        "cache_path": cache_path,
        "ttl_days": ttl_days,
        "generated_at_ts": now_ts,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logging.info(f"business_context_builder: 已生成业务上下文缓存 {cache_path}")
    except Exception as exc:
        logging.warning(f"business_context_builder: 写缓存失败，忽略: {exc}")
    return result
