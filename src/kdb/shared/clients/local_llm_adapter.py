#!/usr/bin/env python
# -*- coding:utf8 -*-
from kdb.shared.config.private_values import private_value as _private_value
'\n本地 / 统一 LLM 适配层。\n\n为知识挖掘侧提供统一的 LLM 调用入口 ``request_knowledge_llm``，内部优先复用\n``agents`` 项目里的 ``commons.llm_client.request_llm``（支持 OpenRouter / OpenAI /\nQwen / Gemini / Volcengine 多渠道、按 model_name 自动路由、主模型失败自动 fallback）。\n\n设计原则（参考 docs/payoneer_article_knowledge_mining_plan.md 与\ndocs/claude_task_generic_mining_context_enrichment.md）：\n\n- 通用挖掘流程不再强绑定 Dify；可以用 Dify 的地方都可以改用本地 LLM。\n- 该适配层是“可选增强”，导入失败 / 配置缺失时应优雅降级，不能让旧流程崩溃。\n- 不在本 repo 复制 llm_client.py，首批通过 sys.path 跨项目引用 agents 项目。\n'

import importlib.util
import json
import logging
import os
import sys
from typing import List, Optional

# agents 项目根目录（包含 commons/llm_client.py）。可用环境变量覆盖，便于部署迁移。
DEFAULT_AGENTS_ROOT = os.environ.get(
    "AGENTS_PROJECT_ROOT", "/Users/chenqishi/stone_fish/agents"
)
DEFAULT_AGENTS_LLM_CONFIG = os.path.join(
    DEFAULT_AGENTS_ROOT, "config", "agent_service_config.json"
)

_PROVIDERS_CONFIGURED = False
_LLM_AVAILABLE: Optional[bool] = None  # None=未检测, True/False=检测结果
_LLM_MODULE = None  # 缓存已加载的 agents llm_client 模块


def _load_agents_llm_client(agents_root: str):
    """直接按文件路径加载 agents 的 llm_client.py。

    注意：本 repo 自带 `commons` 包，直接 `from commons.llm_client import ...` 会与本 repo 的
    commons 命名空间冲突（agents 的 commons 被遮蔽）。因此用 importlib 以独立模块名加载文件，
    避免污染/冲突。llm_client.py 只依赖 stdlib + requests，无 agents 内部相对导入，可独立加载。
    """
    global _LLM_MODULE
    if _LLM_MODULE is not None:
        return _LLM_MODULE
    file_path = os.path.join(agents_root, "commons", "llm_client.py")
    if not os.path.exists(file_path):
        raise ImportError(f"未找到 agents llm_client: {file_path}")
    spec = importlib.util.spec_from_file_location("agents_llm_client", file_path)
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
            logging.warning(f"local_llm_adapter: 无法加载 agents llm_client，降级不可用: {exc}")
        _LLM_AVAILABLE = False
        return None, False

    if not _PROVIDERS_CONFIGURED:
        cfg_path = os.environ.get("AGENTS_LLM_CONFIG", DEFAULT_AGENTS_LLM_CONFIG)
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
    """检测本地 LLM 后端是否可用（agents llm_client 是否可导入）。"""
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
        agents_root: 覆盖 agents 项目根目录。

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
