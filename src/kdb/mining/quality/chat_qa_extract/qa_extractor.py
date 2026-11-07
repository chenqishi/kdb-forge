#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
对话 QA 抽取 —— Dify workflow「对话QA抽取-norm-nomixv1」的本地实现。

原 Dify 流的逻辑（data/对话QA抽取-norm-nomixv1.yml）：
    start(paragraph, system_prompt)
      → if system_prompt 为空 → 默认LLM（内置 system prompt）
                     否则   → 外部入参LLM（用传入的 system_prompt）
      → code: 去掉 <think>...</think>
      → end: Final

本地实现保持同样的分支和输出格式，并在此基础上支持按 client 追加增强规则
（prompts/extract.<client>.md），用于收紧特定客户的抽取口径。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('chat_qa_extract/qa_extractor.py')

import logging
import os
import re
from typing import Optional

from . import config as cqe_config
from . import llm_client

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__legacy_source_file__)), 'prompts')

_THINK_RE = re.compile(r'<think>[\s\S]*?</think>')


def clear_think(result: str) -> str:
    """去掉 <think></think> 及其中内容，对应原 Dify 流的代码节点"""
    if not result:
        return ''
    if '<think>' in result and '</think>' in result:
        result = _THINK_RE.sub('', result)
    return result.strip()


def load_prompt(name: str) -> str:
    """读取 prompts/<name>.md，不存在时返回空串"""
    path = os.path.join(PROMPT_DIR, f'{name}.md')
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().strip()


class ChatQAExtractor(object):
    """
    与 commons.dify_tools.DifyWorkFlowRequest 接口兼容的本地 QA 抽取器。

    调用方仍然用 `.request_dify(paragraph)`，因此可以直接替换原 Dify 客户端。
    """

    def __init__(self, system_prompt: Optional[str] = None, client: Optional[str] = None,
                 model: Optional[str] = None, max_retries: int = 2,
                 max_tokens: int = 16000, temperature: float = 0.2,
                 timeout: int = 180, usage_out: Optional[dict] = None):
        """
        Args:
            system_prompt: 任务侧生成的 system prompt；为空时用 prompts/extract.default.md
            client:        客户名，存在 prompts/extract.<client>.md 时把其内容追加到 system prompt 后
            model:         模型名，默认取配置 models.extract
            max_retries:   LLM 返回空时的额外重试次数
        """
        cqe_config.load_llm_config()
        self.client = client or ''
        self.model = cqe_config.get_model('extract', model)
        self.max_retries = max(1, int(max_retries))
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.usage_out = usage_out

        base_prompt = (system_prompt or '').strip() or load_prompt('extract.default')
        augment = load_prompt(f'extract.{self.client}') if self.client else ''
        if augment:
            logging.info('ChatQAExtractor: client=%s 命中增强规则 extract.%s.md', self.client, self.client)
            self.system_prompt = f'{base_prompt}\n\n{augment}'
        else:
            self.system_prompt = base_prompt

    def request_dify(self, paragraph: str, other_inputs: Optional[dict] = None) -> Optional[str]:
        """
        兼容原 Dify 客户端的入口。

        Returns:
            抽取结果文本；失败返回 None（调用方按"该群跳过"处理）
        """
        if not paragraph:
            raise ValueError('paragraph is empty')

        query = f'以下是对话记录，请进行处理:\n{paragraph}'
        for attempt in range(self.max_retries):
            content, detail = llm_client.request_llm(
                model_name=self.model,
                query=query,
                system_message=self.system_prompt,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
                usage_out=self.usage_out,
            )
            content = clear_think(content)
            if content:
                return content
            logging.warning('ChatQAExtractor: 第 %d 次返回为空, model=%s, prompt_len=%d, detail=%s',
                            attempt + 1, self.model, len(paragraph), detail[:200])

        logging.error('ChatQAExtractor: 抽取失败, model=%s, prompt_len=%d', self.model, len(paragraph))
        return None


def build_extractor(system_prompt: Optional[str] = None, client: Optional[str] = None,
                    **kwargs) -> ChatQAExtractor:
    """工厂函数，便于调用方少 import 一层"""
    return ChatQAExtractor(system_prompt=system_prompt, client=client, **kwargs)
