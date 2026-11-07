#!/usr/bin/env python
# -*- coding:utf8 -*-
from kdb.shared.config.private_values import private_value as _private_value
'\n可选的网络业务背景构建（默认关闭）。\n\n约束（参考 docs/claude_task_generic_mining_context_enrichment.md）：\n- 默认关闭，只有调用方在 enable_web_context=true 时才会调用本模块。\n- 结果只用于客户业务画像 / 术语 / 产品边界 / 目标用户，**不得**直接作为文档知识答案。\n- 必须缓存，避免每次任务都触发检索；缓存按 client + knowledge_objective 命中，TTL 默认 30 天。\n- 当前运行环境若没有可用搜索工具 / 网络失败，返回空上下文并记录 warning，绝不抛异常中断主任务。\n\n实现说明：\n本 repo 当前没有内置实时网络检索工具。为保持“可选增强 + 优雅降级”，本模块通过\n``search_callable`` 钩子接受外部注入的检索函数；未注入时返回空上下文并记录 warning。\n'

import hashlib
import json
import logging
import os
import time
from typing import Callable, Optional


def _cache_key(client: str, knowledge_objective: Optional[str]) -> str:
    raw = f"{client}||{knowledge_objective or ''}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _empty_context(client: str, knowledge_objective: Optional[str], warning: str,
                   cache_path: str) -> dict:
    return {
        "client": client,
        "knowledge_objective": knowledge_objective or "",
        "context_text": "",
        "sources": {"web_search": False},
        "cache_hit": False,
        "cache_path": cache_path,
        "warning": warning,
    }


def build_web_business_context(
    *,
    client: str,
    knowledge_objective: Optional[str] = None,
    cache_dir: str,
    ttl_days: int = 30,
    search_callable: Optional[Callable[[str], str]] = None,
    now_ts: Optional[float] = None,
) -> dict:
    """构建（并缓存）客户网络业务背景。

    Args:
        client: 客户名。
        knowledge_objective: 本次知识目标，参与缓存 key。
        cache_dir: 缓存目录，例如 data/business_context_cache。
        ttl_days: 缓存有效期天数。
        search_callable: 可选检索函数 fn(query)->str；未提供则不发起检索（降级）。
        now_ts: 当前时间戳（便于测试注入），缺省 time.time()。

    Returns:
        dict：含 context_text / sources / cache_hit / cache_path / warning。
        无检索能力时 context_text 为空且带 warning。
    """
    os.makedirs(cache_dir, exist_ok=True)
    key = _cache_key(client, knowledge_objective)
    cache_path = os.path.join(cache_dir, f"web_{key}.json")
    now_ts = now_ts if now_ts is not None else time.time()

    # 命中有效缓存
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            generated_at = cached.get("generated_at_ts", 0)
            if now_ts - generated_at < ttl_days * 86400:
                cached["cache_hit"] = True
                cached["cache_path"] = cache_path
                logging.info(f"web_business_context: 命中缓存 {cache_path}")
                return cached
        except Exception as exc:
            logging.warning(f"web_business_context: 读取缓存失败，忽略: {exc}")

    if search_callable is None:
        warning = "未提供网络检索能力(search_callable)，跳过网络业务背景，返回空上下文"
        logging.warning(f"web_business_context: {warning}")
        return _empty_context(client, knowledge_objective, warning, cache_path)

    # 发起检索（外部注入），失败降级
    query = f"{client} 公司业务 产品 目标用户 {knowledge_objective or ''}".strip()
    try:
        raw = search_callable(query) or ""
    except Exception as exc:
        warning = f"网络检索失败，返回空上下文: {exc}"
        logging.warning(f"web_business_context: {warning}")
        return _empty_context(client, knowledge_objective, warning, cache_path)

    context_text = (raw or "").strip()
    result = {
        "client": client,
        "knowledge_objective": knowledge_objective or "",
        "context_text": context_text,
        "sources": {"web_search": bool(context_text)},
        "cache_hit": False,
        "cache_path": cache_path,
        "warning": "" if context_text else "检索结果为空",
        "generated_at_ts": now_ts,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logging.warning(f"web_business_context: 写缓存失败，忽略: {exc}")
    return result
