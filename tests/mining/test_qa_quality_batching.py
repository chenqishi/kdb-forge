from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""QA 质检分块的行为测试（离线，假 Dify）。

要守住的两条：
  1. 分块后每批的序号要按批偏移换算成**全局序号**，否则标签会挂到别的 QA 上；
  2. `#重复-N` 里的 N 是批内序号，同样要偏移，否则分组串号。

背景：质检原来是整份清单一次调用，条数一多必然对不上——实测 584 条只对上 180 条，
其余 404 条拿不到标签、全部降级；76 条的小文档则完全正常。
"""
import os
import sys

ROOT = str(_PROJECT_ROOT)

import kdb.mining.common.generation.long_qa as kc


class _FakeDify(object):
    """按收到的清单条数，原样回一份带标签的结果，序号从 1 开始（模拟真实行为）。"""

    def __init__(self, tag_of=None, drop_after=None):
        self.calls = []
        self.tag_of = tag_of or (lambda i: '#优质')
        self.drop_after = drop_after      # 模拟「模型少回几条」

    def request_dify(self, qa_text):
        # qajson_to_line_text 的格式：`1.问题:Q1\n答案:A1\n###\n2.问题:Q2\n答案:A2`
        n = len([b for b in qa_text.split('###') if b.strip()])
        self.calls.append(n)
        emit = n if self.drop_after is None else min(n, self.drop_after)
        parts = []
        for i in range(1, emit + 1):
            parts.append('%d.问题:Q%d\n答案:A%d%s' % (i, i, i, self.tag_of(i)))
        return '\n###\n'.join(parts)


def _qa_list(n):
    return [{'q': 'Q%d' % i, 'a': 'A%d' % i} for i in range(1, n + 1)]


def test_batches_are_split_by_size():
    dify = _FakeDify()
    kc.request_quality_info_in_batches(_qa_list(100), dify, batch_size=40)
    assert dify.calls == [40, 40, 20]          # 不再是一次性 100 条


def test_indices_are_global_not_per_batch():
    """第二批的第 1 条，全局序号必须是 41 而不是 1。"""
    dify = _FakeDify()
    info = kc.request_quality_info_in_batches(_qa_list(100), dify, batch_size=40)
    assert len(info) == 100
    assert set(info.keys()) == set(range(1, 101))


def test_duplicate_index_is_offset_to_global():
    """`#重复-2` 出现在第二批时，指向的应是全局第 42 条。"""
    dify = _FakeDify(tag_of=lambda i: '#优质#重复-2' if i == 3 else '#优质')
    info = kc.request_quality_info_in_batches(_qa_list(80), dify, batch_size=40)
    assert info[3]['duplicate_index'] == 2        # 第一批内不变
    assert info[43]['duplicate_index'] == 42      # 第二批偏移 40


def test_partial_batch_does_not_break_other_batches():
    """某一批模型少回条目，只影响该批，其余批照常拿到标签。"""
    dify = _FakeDify(drop_after=10)               # 每批只回 10 条
    info = kc.request_quality_info_in_batches(_qa_list(80), dify, batch_size=40)
    assert len(info) == 20                        # 两批各 10 条
    assert 1 in info and 41 in info               # 两批的首条都在


def test_empty_list_makes_no_call():
    dify = _FakeDify()
    assert kc.request_quality_info_in_batches([], dify, batch_size=40) == {}
    assert dify.calls == []
