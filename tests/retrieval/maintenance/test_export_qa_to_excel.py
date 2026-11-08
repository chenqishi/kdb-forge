from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-

"""export_qa_to_excel 的纯函数单测：查询条件、来源中文标签、类目抽取、行拍平。不打网络。"""

import json
import os
import sys

import pytest

PROJECT_ROOT = str(_PROJECT_ROOT)

from kdb.retrieval.maintenance.excel_export import trans_es_data_to_excel
from kdb.retrieval.maintenance.qa_export import DEFAULT_CATEGORY
from kdb.retrieval.maintenance.qa_export import HEADERS
from kdb.retrieval.maintenance.qa_export import MAX_CELL_LEN
from kdb.retrieval.maintenance.qa_export import build_export_query
from kdb.retrieval.maintenance.qa_export import extract_from_file_name
from kdb.retrieval.maintenance.qa_export import select_headers
from kdb.retrieval.maintenance.qa_export import clean_cell_text
from kdb.retrieval.maintenance.qa_export import export_rows
from kdb.retrieval.maintenance.qa_export import extract_category
from kdb.retrieval.maintenance.qa_export import flatten_doc
from kdb.retrieval.maintenance.qa_export import norm_from_type_label
from kdb.retrieval.maintenance.qa_export import reconcile
from kdb.retrieval.maintenance.qa_export import summarize
from kdb.retrieval.maintenance.qa_export import verify_excel_rows


def _filters(query):
    return query['bool']['filter']


def test_query_filters_source_type_qa_audit_and_not_deleted():
    filters = _filters(build_export_query(['document', 'html', 'manual']))
    assert {'terms': {'from_type_norm': ['document', 'html', 'manual']}} in filters
    assert {'term': {'data_type': 'qa'}} in filters
    assert {'term': {'del_flag': 0}} in filters
    # 「有效」= audit_result > 0，用 gte 1 而不是枚举 [1, 2]，新增取值不会漏
    assert {'range': {'audit_result': {'gte': 1}}} in filters


def test_query_can_include_deleted():
    filters = _filters(build_export_query(['html'], include_deleted=True))
    assert all('del_flag' not in list(f.values())[0] for f in filters)


def test_query_without_source_type_filter():
    filters = _filters(build_export_query([]))
    assert all('from_type_norm' not in list(f.values())[0] for f in filters)


def test_query_all_data_types_exports_segment_too():
    """知识不止 qa：data_type=all 时不能再加 data_type 过滤，否则 segment 整批漏掉。"""
    filters = _filters(build_export_query([], data_type='all'))
    assert all('data_type' not in list(f.values())[0] for f in filters)
    assert {'range': {'audit_result': {'gte': 1}}} in filters


def test_query_multiple_data_types_uses_terms():
    filters = _filters(build_export_query([], data_type='qa,segment'))
    assert {'terms': {'data_type': ['qa', 'segment']}} in filters


@pytest.mark.parametrize('value,expected', [
    ('document', '文档'),
    ('html', '网页'),
    ('manual', '免审录入'),
    # 管理 API 文档里手动录入写的是 manual_input，也是同一档
    ('manual_input', '免审录入'),
    # 存量数据里 from_type_norm 存在中文历史写法，映射到同一个标签
    ('自动学习', '自动学习'),
    ('auto_learning', '自动学习'),
    ('老师培训', '老师培训'),
    ('', ''),
    (None, ''),
])
def test_from_type_label(value, expected):
    assert norm_from_type_label(value) == expected


def test_unknown_from_type_label_is_kept_not_swallowed():
    """认不出来的值要原样透出，否则导出里会出现一批来源为空的行而没人发现。"""
    assert norm_from_type_label('alina修正/新增') == 'alina修正/新增'


def test_category_uses_full_path():
    source = {'primary_category': {
        'cate1_name': '运营问题类型', 'cate2_name': 'Listing管理',
        'category_path': '运营问题类型-Listing管理'}}
    assert extract_category(source) == '运营问题类型-Listing管理'


def test_category_single_level():
    source = {'primary_category': {'cate1_name': '默认分组', 'category_path': '默认分组'}}
    assert extract_category(source) == '默认分组'


def test_category_rebuilds_path_when_category_path_missing():
    """有 cateN_name 但没写 category_path 的存量文档，自己按层级拼全路径。"""
    source = {'primary_category': {
        'cate1_name': 'a', 'cate2_name': 'b', 'cate3_name': 'c', 'cate4_name': 'd'}}
    assert extract_category(source) == 'a-b-c-d'


def test_category_falls_back_to_category_infos_by_score():
    """少量存量文档没有 primary_category，回落到 category_infos 里 score 最高那条。"""
    source = {'category_infos': [
        {'category_name': '低分类目', 'score': 0.2},
        {'category_name': '高分类目', 'score': 0.9},
    ]}
    assert extract_category(source) == '高分类目'


def test_category_missing_everywhere_uses_default():
    """两处都没有类目时给默认类目，导出里不留空。"""
    assert extract_category({}) == DEFAULT_CATEGORY
    assert extract_category({}, default_category='未分类') == '未分类'


def test_from_file_name_comes_from_ext_info():
    """来源链接/文件名在 ext_info 里，不是顶层字段。"""
    url = 'https://vendedores.mercadolivre.com.br/nota/beleza'
    assert extract_from_file_name({'ext_info': {'from_file_name': url}}) == url
    assert extract_from_file_name({'ext_info': {'tags': ['x']}}) == ''
    assert extract_from_file_name({}) == ''


def test_flatten_doc_maps_all_headers():
    row = flatten_doc('id1', {
        'title': '怎么开店？', 'content': '按流程提交资料',
        'dataset': 'mercado', 'data_type': 'segment', 'from_type_norm': 'html',
        'ext_info': {'from_file_name': 'https://example.com/help/1'},
        'insert_time': '2026-03-15 14:59:36', 'update_time': '2026-07-23 22:52:19',
        'audit_result': 2, 'quality_level': 'high',
        'primary_category': {'cate1_name': '业务类型', 'cate2_name': 'FULL仓',
                             'category_path': '业务类型-FULL仓'},
    }, 'mercado_local')
    assert set(row.keys()) == set(HEADERS)
    assert row['_id'] == 'id1'
    assert row['index_name'] == 'mercado_local'
    assert row['from_type_norm'] == '网页'
    assert row['data_type'] == 'segment'
    assert row['from_file_name'] == 'https://example.com/help/1'
    # 录入时间是 insert_time；update_time 会被批量改字段刷成同一个时间，不能拿来当录入时间
    assert row['insert_time'] == '2026-03-15 14:59:36'
    assert row['category_path'] == '业务类型-FULL仓'
    assert row['title'] == '怎么开店？'
    assert row['content'] == '按流程提交资料'


def test_flatten_doc_strips_illegal_xlsx_chars():
    """带控制字符的行在 trans_es_data_to_excel 里会抛错然后被 continue 静默丢掉。"""
    row = flatten_doc('id2', {'title': 'a\x07b', 'content': 'c\x00d'}, 'mercado')
    assert row['title'] == 'ab'
    assert row['content'] == 'cd'


def test_clean_cell_text_truncates_over_excel_limit():
    cleaned = clean_cell_text('x' * (MAX_CELL_LEN + 100))
    assert len(cleaned) <= MAX_CELL_LEN
    assert cleaned.endswith('[已截断]')


def test_clean_cell_text_keeps_non_string():
    assert clean_cell_text(2) == 2
    assert clean_cell_text(None) is None


class _StubEs(object):
    """按索引返回预置文档，只实现 export_rows / reconcile 用到的两个方法。"""

    def __init__(self, docs_by_index):
        self.docs_by_index = docs_by_index

    def iter_search_after(self, index, query, source_fields, page_size=1000, limit=None):
        docs = self.docs_by_index.get(index, [])
        if limit is not None:
            docs = docs[:limit]
        for doc_id, source in docs:
            yield doc_id, source

    def count(self, index, query):
        return len(self.docs_by_index.get(index, []))


def test_export_to_excel_round_trip_keeps_every_row(tmp_path):
    """控制字符 + 超长正文都不能让行在写 Excel 时被静默丢掉。"""
    es = _StubEs({
        'mercado': [
            ('a', {'title': '问题一', 'content': 'x' * (MAX_CELL_LEN + 50),
                   'dataset': 'mercado', 'from_type_norm': 'document', 'audit_result': 2,
                   'primary_category': {'cate1_name': '默认分组', 'category_path': '默认分组'}}),
            ('b', {'title': '问\x07题二', 'content': '答案二',
                   'dataset': 'mercado', 'from_type_norm': 'manual', 'audit_result': 1}),
        ],
        'mercado_local': [
            ('c', {'title': '问题三', 'content': '答案三',
                   'dataset': 'mercado', 'from_type_norm': 'html', 'audit_result': 2}),
        ],
    })
    query = build_export_query(['document', 'html', 'manual'])
    rows_file = str(tmp_path / 'rows.jsonl')
    excel_file = str(tmp_path / 'out.xlsx')

    rows = export_rows(es, ['mercado', 'mercado_local'], query, rows_file)
    assert len(rows) == 3
    assert reconcile(es, ['mercado', 'mercado_local'], query, rows) == {
        'mercado': {'es_count': 2, 'exported': 2},
        'mercado_local': {'es_count': 1, 'exported': 1},
    }

    trans_es_data_to_excel(rows_file, excel_file, headers=HEADERS)
    assert verify_excel_rows(excel_file, 3) == 3

    from openpyxl import load_workbook
    ws = load_workbook(excel_file).active
    assert [c.value for c in ws[1]] == HEADERS
    assert ws.cell(row=3, column=HEADERS.index('title') + 1).value == '问题二'
    assert ws.cell(row=3, column=HEADERS.index('from_type_norm') + 1).value == '免审录入'
    # 没有任何类目信息的那条落到默认类目，不留空
    assert ws.cell(row=3, column=HEADERS.index('category_path') + 1).value == DEFAULT_CATEGORY


def test_reconcile_raises_when_rows_missing(tmp_path):
    es = _StubEs({'mercado': [('a', {'title': 'q'}), ('b', {'title': 'q2'})]})
    query = build_export_query(['html'])
    rows = [flatten_doc('a', {'title': 'q'}, 'mercado')]
    with pytest.raises(RuntimeError, match='行数对账失败'):
        reconcile(es, ['mercado'], query, rows)


def test_verify_excel_rows_raises_on_dropped_rows(tmp_path):
    rows_file = str(tmp_path / 'rows.jsonl')
    excel_file = str(tmp_path / 'out.xlsx')
    with open(rows_file, 'w', encoding='utf-8') as f:
        f.write('{"_id": "a", "title": "q"}\n')
    trans_es_data_to_excel(rows_file, excel_file, headers=HEADERS)
    with pytest.raises(RuntimeError, match='Excel 行数对账失败'):
        verify_excel_rows(excel_file, 2)


def test_select_headers_defaults_to_all():
    assert select_headers(None) == HEADERS
    assert select_headers('all') == HEADERS


def test_select_headers_keeps_requested_order_and_subset():
    assert select_headers('title,content,data_type') == ['title', 'content', 'data_type']


def test_select_headers_rejects_unknown_column():
    """拼错列名 trans_es_data_to_excel 会安静地出一整列空白，必须直接抛错。"""
    with pytest.raises(ValueError, match='未知列'):
        select_headers('title,quality')


def test_selected_columns_written_to_excel(tmp_path):
    rows_file = str(tmp_path / 'rows.jsonl')
    excel_file = str(tmp_path / 'out.xlsx')
    row = flatten_doc('a', {'title': 'q', 'content': 'a', 'data_type': 'qa',
                            'from_type_norm': 'html', 'audit_result': 2,
                            'quality_level': 'high'}, 'mercado')
    with open(rows_file, 'w', encoding='utf-8') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    headers = select_headers('_id,data_type,from_type_norm,title,content')
    trans_es_data_to_excel(rows_file, excel_file, headers=headers)
    from openpyxl import load_workbook
    ws = load_workbook(excel_file).active
    assert [c.value for c in ws[1]] == headers
    assert [c.value for c in ws[2]] == ['a', 'qa', '网页', 'q', 'a']


def test_summarize_counts_by_index_data_type_and_source():
    rows = [
        {'index_name': 'mercado', 'data_type': 'qa', 'from_type_norm': '文档'},
        {'index_name': 'mercado', 'data_type': 'qa', 'from_type_norm': '文档'},
        {'index_name': 'mercado', 'data_type': 'segment', 'from_type_norm': '网页'},
        {'index_name': 'mercado_local', 'data_type': 'qa', 'from_type_norm': '免审录入'},
    ]
    assert summarize(rows) == {
        'mercado': {'qa/文档': 2, 'segment/网页': 1},
        'mercado_local': {'qa/免审录入': 1},
    }
