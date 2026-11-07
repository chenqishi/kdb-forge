"""Unit tests for payoneer_chat_mining.conversation_segmenter."""

from __future__ import annotations

import datetime as _dt

import pytest

from payoneer_chat_mining.conversation_segmenter import segment_group


def _mk(n: int, start: _dt.datetime, step_min: int = 1) -> list[dict]:
    return [{"send_time": start + _dt.timedelta(minutes=step_min * i), "content": f"msg{i}"}
            for i in range(n)]


def test_empty_returns_empty():
    assert segment_group([]) == []


def test_single_message():
    msgs = _mk(1, _dt.datetime(2026, 5, 1, 9, 0))
    out = segment_group(msgs)
    assert out == [msgs]


def test_short_group_kept_whole():
    msgs = _mk(500, _dt.datetime(2026, 5, 1, 9, 0))
    out = segment_group(msgs, long_threshold=500)
    assert len(out) == 1
    assert len(out[0]) == 500


def test_long_group_no_gap_hard_split():
    # 600 messages 1 min apart → no >1day gaps → hard cap kicks in
    msgs = _mk(600, _dt.datetime(2026, 5, 1, 9, 0), step_min=1)
    out = segment_group(msgs, long_threshold=500, time_gap_hours=24, hard_cap=200)
    assert len(out) == 3
    assert all(len(c) == 200 for c in out)
    # ordering preserved
    flat = [m for c in out for m in c]
    assert flat == msgs


def test_long_group_with_time_gap_splits():
    # 300 messages today + 1 day later 250 messages → 550 total > 500 threshold
    base1 = _dt.datetime(2026, 5, 1, 9, 0)
    msgs1 = _mk(300, base1, step_min=1)
    base2 = _dt.datetime(2026, 5, 3, 9, 0)  # 2 days later
    msgs2 = _mk(250, base2, step_min=1)
    msgs = msgs1 + msgs2
    out = segment_group(msgs, long_threshold=500, time_gap_hours=24, hard_cap=400)
    assert len(out) == 2
    assert len(out[0]) == 300
    assert len(out[1]) == 250


def test_long_group_gap_then_hard_split():
    # 600 messages within day1 + 250 in day3 → gap split gives [600, 250],
    # 然后 600 硬切成 200x3，250 硬切成 200+50 → 共 5 段
    base1 = _dt.datetime(2026, 5, 1, 9, 0)
    msgs1 = _mk(600, base1, step_min=1)
    base2 = _dt.datetime(2026, 5, 3, 9, 0)
    msgs2 = _mk(250, base2, step_min=1)
    msgs = msgs1 + msgs2
    out = segment_group(msgs, long_threshold=500, time_gap_hours=24, hard_cap=200)
    assert len(out) == 5
    assert [len(c) for c in out] == [200, 200, 200, 200, 50]


def test_invalid_send_time_raises():
    msgs = [{"send_time": "2026-05-01", "content": "x"}] * 600
    with pytest.raises(TypeError):
        segment_group(msgs, long_threshold=500)
