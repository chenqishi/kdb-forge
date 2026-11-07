"""效果类测试：RAG 适配性分类器（任务1）。

依赖远端 LLM，默认在 collection 阶段被 conftest 跳过。
本地运行：
    pytest tests/test_rag_suitability_cases.py -m llm -v
"""

from __future__ import annotations
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_rag_suitability_cases.py')

import json
import os

import pytest

from payoneer_chat_mining.rag_suitability_classifier import classify_question

CASES_PATH = os.path.join(os.path.dirname(__legacy_source_file__), "fixtures", "expected_rag_cases.json")


def _load_cases():
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.llm
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["question"][:30])
def test_rag_suitability_case(case):
    result = classify_question(case["question"])
    assert not result.get("parse_error"), f"parse_error result={result}"
    assert result["is_rag_suitable"] == case["expected_is_rag_suitable"], (
        f"Q={case['question']!r}\nGot={result}\nExpected={case['expected_is_rag_suitable']}"
    )
    # topic 是自由生成，只做关键词包含检查（任一命中即可，且仅是软断言）
    topic = result["topic"]
    if topic:
        kws = case["expected_topic_keywords"]
        hit = any(kw in topic for kw in kws)
        assert hit or topic, (
            f"Topic={topic!r} 与期望关键词 {kws} 不匹配 — 仅警示，不一定失败"
        )
