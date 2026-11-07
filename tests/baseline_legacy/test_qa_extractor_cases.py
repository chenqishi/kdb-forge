"""效果类测试：QA 抽取器（任务2）。

依赖远端 LLM，默认跳过。本地运行：
    pytest tests/test_qa_extractor_cases.py -m llm -v
"""

from __future__ import annotations

import datetime as _dt

import pytest

from payoneer_chat_mining.qa_extractor import extract_qa_from_scenario


def _build_scenario():
    base = _dt.datetime(2026, 5, 1, 10, 0)
    rows = [
        ("张三", "客户", "请问 Payoneer 提现到工商银行的费率是多少？"),
        ("李四", "员工", "工商银行提现费率一般是 1.2%，最低 3 美元。"),
        ("张三", "客户", "到账时间一般要多久？"),
        ("李四", "员工", "正常情况 1-2 个工作日到账。"),
        ("张三", "客户", "在吗在吗？"),
        ("李四", "员工", "在的，您说。"),
        ("张三", "客户", "我的账户 ID 88812 为啥被冻结？"),
        ("李四", "员工", "稍等我帮您查一下后台。"),
    ]
    msgs = []
    for i, (sender, role, text) in enumerate(rows):
        msgs.append({
            "sender": sender,
            "sender_role": role,
            "receiver": "群A",
            "send_time": base + _dt.timedelta(minutes=i),
            "content": text,
            "msg_type": "文本",
        })
    return msgs


@pytest.mark.llm
def test_extract_finds_general_qa_and_filters_personal():
    scenario = _build_scenario()
    qas = extract_qa_from_scenario(scenario, group_name="群A", scenario_id="群A::seg000")

    assert qas, "应当至少抽出 1 个 QA"
    assert all(not q.get("parse_error") for q in qas), f"存在 parse_error: {qas}"

    # 至少有一个关于费率/到账的高质 + 通用 QA
    good = [q for q in qas if q["is_high_quality"] == "yes" and q["is_general"] == "yes"]
    assert good, f"未找到 高质+通用 QA，全部 QA:\n{qas}"

    # 个人账户冻结相关的 QA 即使被抽出，is_general 也应为 no
    for q in qas:
        if "冻结" in q["q"] or "88812" in q["q"]:
            assert q["is_general"] == "no", f"个人账户问题不应标记为通用: {q}"
