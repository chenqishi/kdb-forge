# -*- coding: utf-8 -*-
"""直连 LLM 的失败语义与调用统计。"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_chat_direct_llm_safety.py')
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.insert(0, ROOT)

from chatknowledge import gen_knowledge_from_chat as gk  # noqa: E402


class _Response:
    def __init__(self, status_code, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_retry_exhaustion_raises_and_records_failed_calls(monkeypatch):
    model = gk.DirectLLMJsonRequest(api_key='test-key', max_retries=2, timeout=1)
    monkeypatch.setattr(
        gk.requests,
        'post',
        lambda *args, **kwargs: _Response(503, text='unavailable')
    )
    monkeypatch.setattr(gk.time, 'sleep', lambda seconds: None)

    with pytest.raises(RuntimeError, match='failed after 2 attempts'):
        model.request_json('测试 prompt')

    stats = model.get_stats()
    assert stats['logical_requests'] == 1
    assert stats['http_attempts'] == 2
    assert stats['successful_requests'] == 0
    assert stats['failed_requests'] == 1
    assert stats['non_200_attempts'] == 2


def test_success_records_token_usage(monkeypatch):
    model = gk.DirectLLMJsonRequest(api_key='test-key', max_retries=1, timeout=1)
    monkeypatch.setattr(
        gk.requests,
        'post',
        lambda *args, **kwargs: _Response(
            200,
            payload={
                'choices': [{'message': {'content': '{"qa": []}'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 4, 'total_tokens': 14},
            },
        )
    )

    assert model.request_json('测试 prompt') == '{"qa": []}'
    stats = model.get_stats()
    assert stats['successful_requests'] == 1
    assert stats['failed_requests'] == 0
    assert stats['prompt_tokens'] == 10
    assert stats['completion_tokens'] == 4
    assert stats['total_tokens'] == 14


def test_missing_model_credential_is_a_hard_failure(monkeypatch):
    for name in (
        'CHATKNOWLEDGE_LLM_API_KEY',
        'DEEPSEEK_API_KEY',
        'OPENAI_API_KEY',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gk, 'config', {})

    model = gk.DirectLLMJsonRequest()
    with pytest.raises(RuntimeError, match='missing LLM api key'):
        model.validate_config()
