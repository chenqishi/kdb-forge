#!/usr/bin/env python
# -*- coding:utf8 -*-
from kdb.shared.config.private_values import private_value as _private_value
"""Optional LLM adapter using an explicitly configured client plugin.

The plugin preserves the existing configure_providers/request_llm protocol.
Missing configuration or plugin failures retain the caller's existing fallback.
"""

import importlib.util
import json
import logging
import os
import sys
from typing import List
from typing import Optional

# Legacy explicit overrides remain accepted; there is no external default checkout.
DEFAULT_AGENTS_ROOT = os.environ.get("AGENTS_PROJECT_ROOT")
DEFAULT_AGENTS_LLM_CONFIG = os.environ.get("KDB_LLM_CONFIG") or os.environ.get("AGENTS_LLM_CONFIG")

_PROVIDERS_CONFIGURED = False
_LLM_AVAILABLE: Optional[bool] = None  # None=未检测, True/False=检测结果
_LLM_MODULE = None  # 缓存已加载的 agents llm_client 模块


def _load_agents_llm_client(agents_root: str):
    """Load the explicitly selected external client without changing sys.path."""
    global _LLM_MODULE
    if _LLM_MODULE is not None:
        return _LLM_MODULE
    file_path = os.environ.get("KDB_LLM_CLIENT_PATH")
    if not file_path and agents_root:
        file_path = os.path.join(agents_root, "commons", "llm_client.py")
    if not file_path:
        raise ImportError("Optional LLM client is not configured; set KDB_LLM_CLIENT_PATH to a compatible client plugin file")
    if not os.path.exists(file_path):
        raise ImportError(f"未找到显式配置的 LLM client 插件: {file_path}")
    spec = importlib.util.spec_from_file_location("kdb_external_llm_client", file_path)
    if spec is None or spec.loader is None:
        raise ImportError("Configured LLM client plugin cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore
    _LLM_MODULE = module
    return module


def _ensure_llm_client(agents_root: Optional[str] = None):
    """加载 agents 的 llm_client，并在首次调用时注入渠道配置。

    返回 (request_llm 函数, 是否可用)。失败时返回 (None, False)，调用方应降级。
    """
    global _PROVIDERS_CONFIGURED, _LLM_AVAILABLE

    root = agents_root or DEFAULT_AGENTS_ROOT

    try:
        module = _load_agents_llm_client(root)
        configure_providers = module.configure_providers
        request_llm = module.request_llm
    except Exception as exc:  # 跨项目加载失败 → 降级
        if _LLM_AVAILABLE is not False:
            logging.warning(f"local_llm_adapter: 无法加载显式 LLM client 插件，降级不可用: {exc}")
        _LLM_AVAILABLE = False
        return None, False

    if not _PROVIDERS_CONFIGURED:
        cfg_path = os.environ.get("KDB_LLM_CONFIG") or os.environ.get("AGENTS_LLM_CONFIG") or DEFAULT_AGENTS_LLM_CONFIG
        try:
            if cfg_path and os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                configure_providers(cfg.get("llm", {}))
                logging.info(f"local_llm_adapter: 已加载 LLM 渠道配置 {cfg_path}")
            else:
                logging.warning(
                    f"local_llm_adapter: 未找到 LLM 渠道配置 {cfg_path}，使用 llm_client 内置默认渠道"
                )
        except Exception as exc:
            logging.warning(f"local_llm_adapter: 加载 LLM 渠道配置失败，使用内置默认: {exc}")
        _PROVIDERS_CONFIGURED = True

    _LLM_AVAILABLE = True
    return request_llm, True


def is_available(agents_root: Optional[str] = None) -> bool:
    """检测显式配置的 LLM client 插件是否可导入。"""
    _, ok = _ensure_llm_client(agents_root)
    return ok


def request_knowledge_llm(
    query: str,
    system_message: str,
    *,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    image_urls: Optional[List[str]] = None,
    temperature: float = 0.1,
    max_tokens: int = 8000,
    usage_out: Optional[dict] = None,
    agents_root: Optional[str] = None,
) -> str:
    """知识挖掘统一 LLM 调用。

    Args:
        query: 用户侧 prompt（通常是待抽取的正文/段落）。
        system_message: 系统 prompt（业务背景 + 抽取规则）。
        model_name: 模型名，空时由底层用 DEFAULT_MODEL；按名称自动路由渠道。
        provider: 显式指定渠道，空时自动检测。
        image_urls: 可选图片 URL 列表（多模态）。
        temperature/max_tokens: 采样参数。
        usage_out: 传入 dict 时回填 token 用量，便于成本统计。
        agents_root: 兼容显式外部 client 根目录；优先使用 KDB_LLM_CLIENT_PATH。

    Returns:
        模型回复文本。后端不可用或调用失败时返回 ""（调用方需降级）。
    """
    request_llm, ok = _ensure_llm_client(agents_root)
    if not ok or request_llm is None:
        logging.warning("local_llm_adapter: LLM 后端不可用，request_knowledge_llm 返回空字符串")
        return ""

    try:
        content, _reasoning, _detail = request_llm(
            model_name=model_name or "",
            query=query,
            system_message=system_message,
            image_urls=image_urls,
            temperature=temperature,
            max_tokens=max_tokens,
            provider=provider,
            usage_out=usage_out,
        )
        return content or ""
    except Exception as exc:
        logging.error(f"local_llm_adapter: request_knowledge_llm 调用异常，降级返回空: {exc}")
        return ""
