#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
chat_qa_extract —— 聊天 QA 抽取与质检的本地实现。

替代原先的两个 Dify workflow：
  - 对话QA抽取-norm-nomixv1  → qa_extractor.ChatQAExtractor
  - qa选择过滤               → quality_filter.QaQualityFilter

两个类都提供与 `commons.dify_tools.DifyWorkFlowRequest` 相同的 `.request_dify(paragraph)`
接口，可直接替换原调用点。

凭证从 `config/llm_config.json` 读取（不入库），模板见 `config/llm_config.json.example`。
"""

from .config import get_model, load_llm_config
from .qa_extractor import ChatQAExtractor, build_extractor, clear_think
from .quality_filter import QaQualityFilter, build_quality_filter

__all__ = [
    'ChatQAExtractor',
    'QaQualityFilter',
    'build_extractor',
    'build_quality_filter',
    'clear_think',
    'get_model',
    'load_llm_config',
]
