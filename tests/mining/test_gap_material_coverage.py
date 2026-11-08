from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""gap_material_coverage / bol_partner_portal_fetch 的纯逻辑单测。

重点覆盖两个**已实际踩过并导致测量结果错误**的坑：
1. 按字符数盲切块 → 块向量代表开头那段而不是块里的答案 → 召回永远够不到
2. 小节标题必须拼进 title 当主题锚，否则同一篇文档的所有块主题不可分

不打网络、不调 embedding、不连库。
"""

import os
import sys

import pytest

PROJECT_ROOT = str(_PROJECT_ROOT)

import kdb.mining.chat.query_analysis.material_coverage as gmc
import kdb.mining.web.sources.bol_partner as bol


# ---------------------------------------------------------------------------
# 按小节切块（核心回归）
# ---------------------------------------------------------------------------

def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding='utf-8')
    return str(tmp_path)


def test_chunks_split_on_section_markers(tmp_path):
    """带 '## ' 标记时必须按小节切，且标题拼进 title。"""
    doc = ('Selling via bol as an EU partner\n\n'
           '## The benefits of selling via bol\n'
           'More reach. Direct access to 13 million customers. ' + 'x' * 150 + '\n\n'
           '## Want to become a partner?\n'
           'Fill in the form. You will receive a one-time invitation link via email. '
           'If you do not hear anything within 5 working days? Then we will not proceed '
           'this time. You are always welcome to try again next year.\n\n')
    d = _write(tmp_path, 'eu.txt', doc)
    chunks = gmc.load_material_chunks(d, min_chars=50)

    titles = [c['title'] for c in chunks]
    assert any('Want to become a partner?' in t for t in titles)
    # 答案所在块的标题必须是它自己那节，而不是隔壁的营销小节
    answer = [c for c in chunks if 'not proceed this time' in c['text']]
    assert len(answer) == 1
    assert 'Want to become a partner?' in answer[0]['title']
    assert 'benefits' not in answer[0]['title']


def test_answer_not_polluted_by_neighbouring_section(tmp_path):
    """回归：答案不能和上一节的营销话术混进同一个块。

    这正是实测踩到的形态——关键句被并进以 'Personal collaboration...' 开头的块，
    块向量代表营销话术，相似度 0.4451 排名 680/2492。
    """
    doc = ('EU partner\n\n'
           '## What you can expect from us\n'
           'Personal collaboration: direct contact with colleagues with local market '
           'knowledge, digital expertise, and the same entrepreneurial spirit. ' + 'y' * 300 + '\n\n'
           '## Want to become a partner?\n'
           'We will not proceed this time. You are always welcome to try again next year.\n\n')
    chunks = gmc.load_material_chunks(_write(tmp_path, 'a.txt', doc), min_chars=40)
    answer = [c for c in chunks if 'try again next year' in c['text']]
    assert len(answer) == 1
    assert 'Personal collaboration' not in answer[0]['text']


def test_long_section_still_splits_but_keeps_heading(tmp_path):
    """超长小节仍要切，但每块都要带小节标题。"""
    long_body = ' '.join(f'Sentence number {i} about invoicing rules.' for i in range(200))
    doc = f'Doc\n\n## Invoice requirements\n{long_body}\n\n'
    chunks = gmc.load_material_chunks(_write(tmp_path, 'b.txt', doc),
                                      chunk_chars=300, min_chars=50)
    assert len(chunks) > 1
    assert all('Invoice requirements' in c['title'] for c in chunks)


def test_falls_back_to_sentence_chunking_without_markers(tmp_path):
    """没有 '## ' 标记的旧格式文件仍要能切（向后兼容）。"""
    doc = 'Old format\n\n' + ' '.join(f'Fact {i} here.' for i in range(80))
    chunks = gmc.load_material_chunks(_write(tmp_path, 'c.txt', doc),
                                      chunk_chars=200, min_chars=50)
    assert chunks
    assert all(c['title'] == 'Old format' for c in chunks)


def test_short_sections_are_dropped(tmp_path):
    doc = 'Doc\n\n## Tiny\ntoo short\n\n'
    assert gmc.load_material_chunks(_write(tmp_path, 'd.txt', doc), min_chars=120) == []


# ---------------------------------------------------------------------------
# 关键词召回
# ---------------------------------------------------------------------------

def test_query_keywords_maps_chinese_terms_to_english():
    kws = gmc.query_keywords('这个波兰发票怎么开呢？是不是有vat就可以开？')
    assert 'invoice' in kws
    assert 'vat' in kws
    assert 'poland' in kws or 'polish' in kws


def test_recall_prefers_title_matches():
    chunks = [
        {'source': 'a.txt', 'title': 'Random page', 'text': 'invoice ' * 20},
        {'source': 'b.txt', 'title': 'Invoice for business customers', 'text': 'other text'},
    ]
    top = gmc.recall_chunks('发票怎么开', chunks, top_k=2)
    assert top[0]['source'] == 'b.txt'      # 标题命中加权后应排第一


def test_recall_returns_empty_without_keywords():
    assert gmc.recall_chunks('？？？', [{'source': 'a', 'title': 't', 'text': 'x'}]) == []


# ---------------------------------------------------------------------------
# HTML 小节抽取
# ---------------------------------------------------------------------------

def test_extract_sections_splits_by_heading():
    raw = ('<html><body><h1>Page title</h1>'
           '<p>intro text that is long enough</p>'
           '<h2>Want to become a partner?</h2>'
           '<p>You will receive a one-time invitation link via email.</p>'
           '<h2>Other section</h2><p>unrelated body</p>'
           '</body></html>')
    secs = bol.extract_sections(raw)
    heads = [h for h, _ in secs]
    assert 'Want to become a partner?' in heads
    body = dict(secs)['Want to become a partner?']
    assert 'one-time invitation link' in body
    assert 'unrelated body' not in body


def test_extract_sections_skips_empty_headings():
    raw = '<h2></h2><p>orphan</p><h2>Real</h2><p>content here</p>'
    assert [h for h, _ in bol.extract_sections(raw)] == ['Real']


def test_extract_sections_returns_empty_without_headings():
    assert bol.extract_sections('<p>just a paragraph</p>') == []


def test_extract_title_strips_site_suffix():
    assert bol.extract_title('<title>Sales Invoice | Partnerplatform</title>') == 'Sales Invoice'


def test_extract_links_dedups_and_keeps_order():
    raw = '<a href="/en/idp/b"></a><a href="/en/idp/a"></a><a href="/en/idp/b"></a>'
    assert bol.extract_links(raw) == ['/en/idp/b', '/en/idp/a']


# ---------------------------------------------------------------------------
# JSON 解析（模型输出容错）
# ---------------------------------------------------------------------------

def test_extract_json_handles_fence_and_prose():
    assert gmc._extract_json('```json\n{"verdict":"covered"}\n```')['verdict'] == 'covered'
    assert gmc._extract_json('{"verdict":"missing"} 以上。')['verdict'] == 'missing'


def test_extract_json_repairs_unclosed_brace():
    out = gmc._extract_json('{"verdict":"partial","reason":"x"')
    assert out and out['verdict'] == 'partial'


def test_extract_json_returns_none_on_garbage():
    assert gmc._extract_json('not json at all') is None


# ---------------------------------------------------------------------------
# 缺口 CSV 读取
# ---------------------------------------------------------------------------

def test_load_gap_queries_filters_platform_and_dedups(tmp_path):
    csv_path = tmp_path / 'gap.csv'
    csv_path.write_text(
        '类别,归属平台(已纠正),知识主题,客户原话,时间\n'
        'P-公开知识库类,Bol,入驻流程与进度规则,那个链接有有效期吗,2026-03-13\n'
        'P-公开知识库类,Bol,入驻流程与进度规则,那个链接有有效期吗,2026-03-14\n'
        'P-公开知识库类,Allegro,物流与仓储,库存在哪个国家,2026-03-15\n',
        encoding='utf-8-sig')
    rows = gmc.load_gap_queries(str(csv_path), 'Bol')
    assert len(rows) == 1            # 同一原话去重
    assert rows[0]['platform'] == 'Bol'


# ---------------------------------------------------------------------------
# 向量缓存：语料变了必须失效，否则会拿旧向量配新块（静默错位）
# ---------------------------------------------------------------------------

def test_vec_cache_key_changes_when_corpus_changes(tmp_path):
    d = tmp_path / 'mat'
    d.mkdir()
    (d / 'a.txt').write_text('title\n\n## Sec\n' + 'x' * 300, encoding='utf-8')
    key1 = gmc._vec_cache_path(str(d))

    (d / 'b.txt').write_text('title\n\n## Sec\n' + 'y' * 300, encoding='utf-8')
    key2 = gmc._vec_cache_path(str(d))
    assert key1 != key2                      # 新增文件 → 缓存 key 变

    (d / 'b.txt').write_text('title\n\n## Sec\n' + 'y' * 900, encoding='utf-8')
    key3 = gmc._vec_cache_path(str(d))
    assert key3 != key2                      # 文件大小变 → 缓存 key 变


def test_vec_cache_key_stable_for_same_corpus(tmp_path):
    d = tmp_path / 'mat'
    d.mkdir()
    (d / 'a.txt').write_text('title\n\n## Sec\n' + 'x' * 300, encoding='utf-8')
    assert gmc._vec_cache_path(str(d)) == gmc._vec_cache_path(str(d))
