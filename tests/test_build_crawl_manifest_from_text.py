#!/usr/bin/env python
# -*- coding:utf8 -*-
"""灌库前质量闸门的单测。

两个回归都是实测踩过的过滤误杀：
1. "From 1 February 2021"（过去生效日）被当成时效性 → 整片丢掉 assortment-policy
2. partner-non-eu 只有 364 字符被当成过短丢掉 → 丢掉非欧盟卖家 VAT 规则入口
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_build_crawl_manifest_from_text.py')

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data_control_tools import build_crawl_manifest_from_text as gate


# --- 时效性判定 ---------------------------------------------------------------

def test_future_effective_date_is_timely():
    assert gate.is_timely('Assortment policy', 'From 1 April 2026 new rules apply.')[0]


def test_past_effective_date_is_not_timely():
    """回归：过去生效日说明规则长期有效，不该被当成会过期的公告。"""
    assert not gate.is_timely('Assortment policy DIY',
                              'From 1 February 2021 these rules apply to all items.')[0]


def test_holiday_campaign_is_timely():
    assert gate.is_timely('Advertising holidays 25', 'body')[0]
    assert gate.is_timely('Webinar: scaling via bol', 'body')[0]


def test_plain_policy_page_is_not_timely():
    assert not gate.is_timely('Invoice for business customers',
                              'When you deliver to a business customer you must issue an invoice.')[0]


# --- 短页豁免 -----------------------------------------------------------------

def test_short_but_relevant_page_is_kept():
    """回归：partner-non-eu 短但是非欧盟 VAT 规则入口，不能丢。"""
    assert gate._is_worth_keeping_short(
        'Partner established in a non-EU country',
        'If you sell via bol and your company is based outside the EU, '
        'specific VAT and invoicing rules apply to you. ' * 2)


def test_short_and_irrelevant_page_not_exempted():
    assert not gate._is_worth_keeping_short('Thank you', 'short body')


def test_too_short_even_if_relevant_not_exempted():
    assert not gate._is_worth_keeping_short('VAT rules', 'tiny')


# --- 端到端 -------------------------------------------------------------------

def _doc(d, name, title, body):
    (d / name).write_text(f'{title}\n\n{body}\n', encoding='utf-8')


def test_load_and_write_manifest(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    _doc(src, 'good.txt', 'Invoice requirements', 'x' * 600)
    _doc(src, 'holiday.txt', 'Advertising holidays 25', 'y' * 600)
    _doc(src, 'tiny.txt', 'Thank you', 'z' * 50)
    _doc(src, 'shortvat.txt', 'VAT treatment abroad', 'w' * 200)

    docs, stats = gate.load_text_docs(str(src), min_chars=400)
    kept = {d['slug'] for d in docs}
    assert 'good' in kept
    assert 'shortvat' in kept          # 短但相关 → 豁免
    assert 'holiday' not in kept       # 时效性 → 丢
    assert 'tiny' not in kept          # 过短且不相关 → 丢
    assert stats['kept'] == 2

    out = tmp_path / 'out'
    path = gate.write_manifest(docs, str(out), 'Bol', 'bol-test')
    manifest = json.load(open(path, encoding='utf-8'))
    assert len(manifest['docs']) == 2
    rec = manifest['docs'][0]
    assert rec['status'] == 'ok' and rec['platform'] == 'Bol'
    # build_doc_mining_tasks 要求每个目录有 content.md + meta.json
    assert os.path.exists(os.path.join(rec['dir'], 'content.md'))
    assert os.path.exists(os.path.join(rec['dir'], 'meta.json'))
