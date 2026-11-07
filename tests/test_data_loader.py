"""Unit tests for payoneer_chat_mining.data_loader."""

from __future__ import annotations

import datetime as _dt

import pytest

from payoneer_chat_mining.data_loader import load_and_group_chat


def test_groups_and_sorts(mini_chat_xlsx):
    groups = load_and_group_chat(mini_chat_xlsx)
    assert set(groups.keys()) == {"群A", "群B"}

    a = groups["群A"]
    # 群A 6 行（1 行 NaN role），drop_nan_role 默认为 True → 5 条
    assert len(a) == 5

    # sorted ascending by send_time
    times = [m["send_time"] for m in a]
    assert times == sorted(times)


def test_role_and_type_preserved(mini_chat_xlsx):
    groups = load_and_group_chat(mini_chat_xlsx)
    a = groups["群A"]
    roles = {m["sender_role"] for m in a}
    msg_types = {m["msg_type"] for m in a}
    assert "客户" in roles
    assert "员工" in roles
    assert "文本" in msg_types
    assert "图片" in msg_types or "链接" in msg_types


def test_drop_nan_role_disabled_keeps_all(mini_chat_xlsx):
    groups = load_and_group_chat(mini_chat_xlsx, drop_nan_role=False)
    # 群A 6 行（含 NaN role）；群B 1 行
    assert len(groups["群A"]) == 6
    assert len(groups["群B"]) == 1


def test_missing_column_raises(tmp_path):
    import pandas as pd
    df = pd.DataFrame({"foo": [1]})
    p = tmp_path / "bad.xlsx"
    df.to_excel(p, index=False)
    with pytest.raises(KeyError):
        load_and_group_chat(str(p))


def test_send_time_is_datetime(mini_chat_xlsx):
    groups = load_and_group_chat(mini_chat_xlsx)
    for msgs in groups.values():
        for m in msgs:
            assert isinstance(m["send_time"], _dt.datetime)
