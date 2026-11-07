#!/usr/bin/env python
# -*- coding:utf8 -*-
"""缺口 query 跨方法对齐的单测（纯逻辑，不读外部文件）。"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_align_gap_queries.py')

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from query_understanding_analysis import align_gap_queries as agq


def test_normalize_strips_punct_and_case():
    assert agq.normalize('Bol 入驻，需要什么？') == agq.normalize('bol入驻需要什么')


def test_char_dice_identical_and_disjoint():
    assert agq.char_dice('abc', 'abc') == 1.0
    assert agq.char_dice('abc', 'xyz') == 0.0
    assert agq.char_dice('', 'abc') == 0.0


def test_align_exact_match_wins():
    peer = [{'key': 'pp:1', 'platform': 'Bol', 'category': 'P', 'topic': 't',
             'query': '入驻需要什么资料？', 'norm': agq.normalize('入驻需要什么资料？')}]
    local = [{'query': '入驻需要什么资料', 'norm': agq.normalize('入驻需要什么资料'),
              'verdict': 'covered', 'top_score': 0.9, 'top_title': 'x', 'count': 1}]
    m, stats = agq.align(peer, local)
    assert stats['exact'] == 1
    assert m[0]['local_verdict'] == 'covered'


def test_align_reports_miss_rather_than_forcing_a_match():
    """阈值以下必须判未命中——错配会让两边判定张冠李戴。"""
    peer = [{'key': 'pp:2', 'platform': 'Bol', 'category': 'P', 'topic': 't',
             'query': '发票怎么开', 'norm': agq.normalize('发票怎么开')}]
    local = [{'query': '物流时效多久', 'norm': agq.normalize('物流时效多久'),
              'verdict': 'missing', 'top_score': 0.1, 'top_title': '', 'count': 1}]
    m, stats = agq.align(peer, local, dice_threshold=0.75)
    assert stats['none'] == 1
    assert m[0]['match_type'] == 'none' and m[0]['local_verdict'] == ''


def test_align_fuzzy_match_on_near_duplicate():
    peer = [{'key': 'pp:3', 'platform': 'Bol', 'category': 'P', 'topic': 't',
             'query': '这个链接有有效期吗', 'norm': agq.normalize('这个链接有有效期吗')}]
    local = [{'query': '那个链接有有效期吗？', 'norm': agq.normalize('那个链接有有效期吗？'),
              'verdict': 'partial', 'top_score': 0.8, 'top_title': 'y', 'count': 2}]
    m, stats = agq.align(peer, local, dice_threshold=0.75)
    assert stats['fuzzy'] == 1
    assert m[0]['local_verdict'] == 'partial'


def test_load_peer_gaps_filters_platform(tmp_path):
    p = tmp_path / 'gap.csv'
    p.write_text('key,平台(已纠正),类别P/T,知识主题,query原文\n'
                 'pp:1,Bol,P,入驻,链接有效期吗\n'
                 'pp:2,Allegro,P,物流,库存在哪\n', encoding='utf-8-sig')
    rows = agq.load_peer_gaps(str(p), platform='Bol')
    assert len(rows) == 1 and rows[0]['key'] == 'pp:1'
