"""Pytest 共享配置 & fixture for payoneer_chat_mining tests."""

from __future__ import annotations
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/conftest.py')

import datetime as _dt
import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__legacy_source_file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "llm: tests that call remote LLM endpoint (skipped by default)"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m"):
        return
    skip_llm = pytest.mark.skip(reason="LLM-dependent test; run with `pytest -m llm`")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)


@pytest.fixture
def mini_chat_xlsx(tmp_path):
    """Generate a small Payoneer-shaped Excel fixture for data_loader tests."""
    import pandas as pd

    base = _dt.datetime(2026, 5, 1, 10, 0, 0)

    rows = [
        # group A — customer & employee back-and-forth
        ("张三", "客户", "群A", None, "群聊", base + _dt.timedelta(minutes=1),
         "Payoneer 提现到工行的费率是多少？", "文本", "tbl1"),
        ("李四", "员工", "群A", None, "群聊", base + _dt.timedelta(minutes=2),
         "提现到工商银行手续费一般是1.2%，最低3美元。", "文本", "tbl1"),
        ("张三", "客户", "群A", None, "群聊", base + _dt.timedelta(minutes=3),
         "[图片消息]", "图片", "tbl1"),
        # group B — employee only (no QA candidate)
        ("王五", "员工", "群B", None, "群聊", base + _dt.timedelta(minutes=4),
         "提醒下大家今天系统维护。", "文本", "tbl1"),
        # NaN role (should be dropped when drop_nan_role=True)
        ("机器人", None, "群A", None, "群聊", base + _dt.timedelta(minutes=5),
         "自动通知", "文本", "tbl1"),
        # group A out-of-order — should be resorted
        ("张三", "客户", "群A", None, "群聊", base + _dt.timedelta(minutes=0),
         "你好，在吗？", "文本", "tbl1"),
        # link message
        ("李四", "员工", "群A", None, "群聊", base + _dt.timedelta(minutes=6),
         "https://payoneer.com/help", "链接", "tbl1"),
    ]
    df = pd.DataFrame(rows, columns=[
        "Content.发送人", "Content.发送人角色", "Content.接收人", "Content.接收人角色",
        "Content.聊天类型", "Content.发送时间", "Content.消息内容", "Content.发送类型",
        "Name",
    ])
    path = tmp_path / "mini_chat.xlsx"
    df.to_excel(path, index=False)
    return str(path)
