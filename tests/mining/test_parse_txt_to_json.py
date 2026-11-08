from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""`wordtotext.parse_txt_to_json` 的分页行为。

回归背景：页面为空时原来会**无条件收下**当前元素，于是单个超长元素只要落在页首
就原样成为一整页，下面「单段超限则按句子分割」的分支永远够不着。
实测一张 32 万字的表格（整表是一个文本元素）就这样变成 1 页，
QA 生成和段落生成把整页送给 Dify，双双撞上 128000 字符上限而失败。
"""
import json
import os
import sys

import pytest


wordtotext = pytest.importorskip('kdb.mining.common.parsing.documents',
                                 reason='wordtotext 依赖 docx/fitz，环境缺时跳过')


def _parse(tmp_path, content, limit=100):
    src = tmp_path / 'doc.md'
    src.write_text(content, encoding='utf-8')
    return json.loads(wordtotext.parse_txt_to_json(str(src), str(tmp_path / 'data'),
                                                   page_char_limit=limit))


def test_oversized_first_element_is_split_not_kept_as_one_page(tmp_path):
    """整篇就是一个超长段落时，也必须分页——这是 32 万字表格挂掉的直接原因。"""
    content = '\n'.join('第%d行的内容占位文本。' % i for i in range(200))
    pages = _parse(tmp_path, content, limit=100)
    assert len(pages) > 1, '超长首元素被原样留成了一页'
    for key, blocks in pages.items():
        n = sum(wordtotext._count_text_length(b.get('text_content') or '') for b in blocks)
        assert n <= 100 * 2, '第 %s 页仍然超限太多：%d' % (key, n)


def test_content_is_preserved_across_pages(tmp_path):
    """分页只能切，不能丢内容。"""
    lines = ['唯一标记%d。' % i for i in range(120)]
    pages = _parse(tmp_path, '\n'.join(lines), limit=80)
    merged = ''.join(b.get('text_content') or ''
                     for key in sorted(pages, key=int) for b in pages[key])
    for line in lines:
        assert line in merged


def test_short_document_stays_single_page(tmp_path):
    pages = _parse(tmp_path, '很短的一段话。', limit=100)
    assert len(pages) == 1
