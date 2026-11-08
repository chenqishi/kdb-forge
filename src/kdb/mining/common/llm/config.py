from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
chat_qa_extract 的配置加载。

真实凭证放在 `config/llm_config.json`（已在 .gitignore 中，不入库），
仓库里只提交 `config/llm_config.json.example` 作为模板。

配置优先级（后者覆盖前者）：
  1. config/llm_config.json
  2. 环境变量 CHAT_QA_EXTRACT_LLM_CONFIG 指定的文件
  3. 环境变量 OPENROUTER_API_URL / OPENROUTER_API_KEY
"""

import json
import logging
import os
import threading
from typing import Any
from typing import Dict
from typing import Optional

import kdb.mining.common.llm.client as llm_client

PROJECT_ROOT = str(_PROJECT_ROOT)
DEFAULT_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'config', 'llm_config.json')

# 各环节的默认模型。抽取用强模型保证质量，质检也不能用太弱的模型——
# 原 Dify 流质检用 gemini-2.5-flash-lite，在长清单上大面积漏条导致标签丢失。
DEFAULT_EXTRACT_MODEL = 'anthropic/claude-sonnet-4'
DEFAULT_QUALITY_MODEL = 'google/gemini-2.5-flash'

_lock = threading.Lock()
_loaded = False
_config: Dict[str, Any] = {}


def _read_config_file(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logging.error('读取 LLM 配置失败 path=%s err=%s', path, e)
        return {}


def _config_from_env() -> Dict[str, Any]:
    api_url = os.environ.get('OPENROUTER_API_URL')
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return {}
    provider: Dict[str, str] = {'api_key': api_key}
    if api_url:
        provider['api_url'] = api_url
    return {'providers': {'openrouter': provider}}


def load_llm_config(config_path: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """
    加载并注入 LLM 配置，进程内只会真正执行一次（除非 force=True）。

    Returns:
        合并后的配置 dict；没有任何可用凭证时返回空 dict 并记 error 日志
    """
    global _loaded, _config
    with _lock:
        if _loaded and not force:
            return _config

        merged: Dict[str, Any] = {}
        for path in (config_path or DEFAULT_CONFIG_PATH,
                     os.environ.get('CHAT_QA_EXTRACT_LLM_CONFIG')):
            cfg = _read_config_file(path) if path else {}
            if cfg:
                _merge(merged, cfg)

        env_cfg = _config_from_env()
        if env_cfg:
            _merge(merged, env_cfg)

        if merged:
            llm_client.configure_providers(merged)
        if not llm_client.is_configured():
            logging.error(
                'LLM 配置缺失：请从 config/llm_config.json.example 复制出 '
                'config/llm_config.json 并填入真实凭证，或设置 OPENROUTER_API_KEY 环境变量')

        _config = merged
        _loaded = True
        return _config


def _merge(base: Dict[str, Any], other: Dict[str, Any]) -> None:
    """两层深合并：providers 逐渠道合并，其余顶层字段直接覆盖"""
    for k, v in other.items():
        if k == 'providers' and isinstance(v, dict):
            providers = base.setdefault('providers', {})
            for name, cfg in v.items():
                if isinstance(cfg, dict):
                    providers.setdefault(name, {}).update(cfg)
        else:
            base[k] = v


def get_model(stage: str, override: Optional[str] = None) -> str:
    """
    取某个环节使用的模型名。

    Args:
        stage: 'extract' 或 'quality'
        override: 显式指定则直接返回

    优先级：override > 配置 models.<stage> > 模块默认
    """
    if override:
        return override
    cfg = load_llm_config()
    from_cfg = (cfg.get('models') or {}).get(stage)
    if from_cfg:
        return from_cfg
    return DEFAULT_EXTRACT_MODEL if stage == 'extract' else DEFAULT_QUALITY_MODEL
