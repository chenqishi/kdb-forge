from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""
chat_qa_extract 的行为测试（全部用假 LLM，不打真实接口）。

重点是质检的**条数对齐**：下游 parse_qa_quality_result 忽略模型打印的序号、
按出现顺序重新编号，所以模型少回一条，其后的 QA 全部错位并被强制降级 mid。
"""
import os
import sys

import pytest

ROOT = str(_PROJECT_ROOT)

from kdb.mining.quality.chat_qa_extract import qa_extractor
from kdb.mining.quality.chat_qa_extract import quality_filter
from kdb.shared.text import qa_text_tools


def _qa_text(n, start=1):
    """造 n 条编号 QA，格式与 schema_trans.qajson_to_line_text(add_index=True) 一致"""
    return '\n###\n'.join(
        f'{i}.问题:第{i}个问题是什么？\n答案:第{i}个答案。' for i in range(start, start + n))


# --- clear_think ---------------------------------------------------------

@pytest.mark.parametrize('raw,expected', [
    ('<think>推理过程</think>问题:a\n答案:b', '问题:a\n答案:b'),
    ('  问题:a\n答案:b  ', '问题:a\n答案:b'),
    ('', ''),
])
def test_clear_think(raw, expected):
    assert qa_extractor.clear_think(raw) == expected


def test_clear_think_keeps_unpaired_tag():
    """只有半个标签时不做删除，避免误删正文"""
    raw = '答案里提到了 <think> 这个词'
    assert qa_extractor.clear_think(raw) == raw


# --- 分块切分 -------------------------------------------------------------

def test_split_qa_blocks_counts_match():
    blocks = quality_filter.split_qa_blocks(_qa_text(7))
    assert len(blocks) == 7
    assert blocks[0].startswith('1.问题:')


def test_split_qa_blocks_ignores_empty_segments():
    text = '1.问题:a\n答案:b\n###\n\n###\n2.问题:c\n答案:d'
    assert len(quality_filter.split_qa_blocks(text)) == 2


# --- 条数对齐（核心） -----------------------------------------------------

class _FakeLLM:
    """按预设脚本返回结果的假 LLM，记录每次收到的 query"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return (self.responses.pop(0) if self.responses else ''), ''


@pytest.fixture
def patch_llm(monkeypatch):
    def _apply(responses):
        fake = _FakeLLM(responses)
        monkeypatch.setattr(quality_filter.llm_client, 'request_llm', fake)
        monkeypatch.setattr(quality_filter.cqe_config, 'load_llm_config', lambda *a, **k: {})
        monkeypatch.setattr(quality_filter.cqe_config, 'get_model', lambda *a, **k: 'fake-model')
        return fake
    return _apply


def test_batches_are_split_by_batch_size(patch_llm):
    """10 条 + batch_size=4 → 分 3 批（4/4/2），每批 query 里带上本批条数"""
    fake = patch_llm([_qa_text(4, 1), _qa_text(4, 5), _qa_text(2, 9)])
    f = quality_filter.QaQualityFilter(batch_size=4)
    out = f.request_dify(_qa_text(10))

    assert len(fake.calls) == 3
    assert quality_filter.count_qa_blocks(out) == 10
    assert '共 4 条 QA' in fake.calls[0]['query']
    assert '共 2 条 QA' in fake.calls[2]['query']


def test_short_response_triggers_retry(patch_llm):
    """模型第一次少回一条 → 重试；重试正确则采用重试结果"""
    fake = patch_llm([_qa_text(3), _qa_text(5)])
    f = quality_filter.QaQualityFilter(batch_size=5, max_retries=2)
    out = f.request_dify(_qa_text(5))

    assert len(fake.calls) == 2
    assert quality_filter.count_qa_blocks(out) == 5


def test_persistent_misalignment_falls_back_to_untagged(patch_llm):
    """重试后仍对不上 → 该批退化为原文无标签，条数依然对齐，不污染其它批"""
    fake = patch_llm([_qa_text(2), _qa_text(2)])
    f = quality_filter.QaQualityFilter(batch_size=5, max_retries=2)
    out = f.request_dify(_qa_text(5))

    assert len(fake.calls) == 2
    assert quality_filter.count_qa_blocks(out) == 5
    # 退化输出不带任何标签
    info = qa_text_tools.parse_qa_quality_result(out)
    assert len(info) == 5
    assert all(not v['tags'] for v in info.values())


def test_downstream_indices_stay_aligned_when_one_batch_fails(patch_llm):
    """
    一批失败不能让后面的批错位——这正是原 Dify 流最致命的问题。
    第 1 批失败退化，第 2 批正常带标签，解析后标签必须落在第 4-6 条上。
    """
    tagged = '\n###\n'.join(
        f'{i}.问题:第{i}个问题是什么？\n答案:第{i}个答案。#优质' for i in range(4, 7))
    fake = patch_llm([_qa_text(1), _qa_text(1), tagged])
    f = quality_filter.QaQualityFilter(batch_size=3, max_retries=2)
    out = f.request_dify(_qa_text(6))

    info = qa_text_tools.parse_qa_quality_result(out)
    assert len(info) == 6
    assert [i for i, v in info.items() if '优质' in v['tags']] == [4, 5, 6]


def test_empty_input_returns_none(patch_llm):
    patch_llm([])
    f = quality_filter.QaQualityFilter()
    assert f.request_dify('') is None


# --- client 增强规则 ------------------------------------------------------

def test_joint_login_augment_is_appended(monkeypatch):
    monkeypatch.setattr(qa_extractor.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(qa_extractor.cqe_config, 'get_model', lambda *a, **k: 'fake-model')

    base = qa_extractor.ChatQAExtractor(system_prompt='原始任务提示词', client=None)
    aug = qa_extractor.ChatQAExtractor(system_prompt='原始任务提示词', client='joint_login')

    assert base.system_prompt == '原始任务提示词'
    assert aug.system_prompt.startswith('原始任务提示词')
    assert len(aug.system_prompt) > len(base.system_prompt)
    assert 'Client Delta v20260905-joint_login' in aug.system_prompt


def test_unknown_client_keeps_base_prompt(monkeypatch):
    """没有对应增强文件的客户，提示词保持原样——存量客户不受影响"""
    monkeypatch.setattr(qa_extractor.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(qa_extractor.cqe_config, 'get_model', lambda *a, **k: 'fake-model')

    ex = qa_extractor.ChatQAExtractor(system_prompt='原始任务提示词', client='no_such_client')
    assert ex.system_prompt == '原始任务提示词'


def test_empty_system_prompt_falls_back_to_default(monkeypatch):
    """对应原 Dify 流的 if-else：system_prompt 为空走内置默认提示词"""
    monkeypatch.setattr(qa_extractor.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(qa_extractor.cqe_config, 'get_model', lambda *a, **k: 'fake-model')

    ex = qa_extractor.ChatQAExtractor(system_prompt=None)
    assert 'Chat QA Extract Prompt v20260905-base' in ex.system_prompt
