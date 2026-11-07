"""
Tests for Excel column mapping (schema_trans.map_excel_columns)
and unstructured Excel parsing (wordtotext.parse_excel_to_json).
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_excel_parsing.py')
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

def _make_stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# Stub server-only / not-installed dependencies before any project imports.
_make_stub('openpyxl_image_loader', SheetImageLoader=None)
_make_stub('PyPDF2')
_make_stub('fitz')
_make_stub('docx2pdf', convert=None)

# python-docx is a package with sub-modules; stub each needed sub-path.
_docx_pkg = _make_stub('docx', Document=None)
_docx_pkg.__path__ = []  # mark as package
_make_stub('docx.oxml', parse_xml=lambda *a, **kw: None)
_docx_oxml_ns = _make_stub('docx.oxml.ns', nsdecls=lambda *a, **kw: {})

# PIL is usually available; if not, stub it.
try:
    from PIL import Image  # noqa: F401
except ImportError:
    _pil = _make_stub('PIL')
    _pil.__path__ = []
    _make_stub('PIL.Image', open=None)

# commons.common_utils may not resolve cleanly in isolation
if 'commons.common_utils' not in sys.modules:
    _make_stub('commons.common_utils', load_map_dict=lambda *a, **kw: {})

from openpyxl import Workbook

from commons.schema_trans import (
    classify_excel_upload,
    map_excel_columns,
    trans_review_excel_to_json_file,
    trans_web_excel_to_json_file,
)
from knowledge_clear_tool.wordtotext import parse_excel_to_json


def _make_xlsx(path, headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)


# ---------------------------------------------------------------------------
# map_excel_columns
# ---------------------------------------------------------------------------

class TestMapExcelColumns:
    def test_canonical_headers(self):
        headers = ['title', 'content', 'indexes', 'synonyms_title']
        result = map_excel_columns(headers)
        assert result is not None
        assert result['title'] == 0
        assert result['content'] == 1
        assert result['indexes'] == 2
        assert result['synonyms_title'] == 3

    def test_chinese_alias_headers(self):
        headers = ['问题', '答案', '检索词']
        result = map_excel_columns(headers)
        assert result is not None
        assert result['title'] == 0
        assert result['content'] == 1
        assert result['indexes'] == 2

    def test_english_alias_question_answer(self):
        headers = ['Question', 'Answer']
        result = map_excel_columns(headers)
        assert result is not None
        assert result['title'] == 0
        assert result['content'] == 1

    def test_mixed_canonical_and_alias(self):
        # title canonical + Answer alias
        headers = ['title', 'Answer', '检索词']
        result = map_excel_columns(headers)
        assert result is not None
        assert result['title'] == 0
        assert result['content'] == 1

    def test_unmappable_returns_none(self):
        headers = ['col_a', 'col_b', 'col_c']
        result = map_excel_columns(headers)
        assert result is None

    def test_missing_content_returns_none(self):
        headers = ['title', 'some_other_col']
        result = map_excel_columns(headers)
        assert result is None

    def test_missing_title_returns_none(self):
        headers = ['some_col', 'content']
        result = map_excel_columns(headers)
        assert result is None

    def test_none_headers_skipped(self):
        headers = [None, 'title', None, 'content']
        result = map_excel_columns(headers)
        assert result is not None
        assert result['title'] == 1
        assert result['content'] == 3


# ---------------------------------------------------------------------------
# classify_excel_upload
# ---------------------------------------------------------------------------

class TestClassifyExcelUpload:
    def test_standard_title_content_excel(self, tmp_path):
        xlsx_file = str(tmp_path / 'standard title content.xlsx')
        _make_xlsx(xlsx_file, ['title', 'content'], [['Q1', 'A1']])

        result = classify_excel_upload(xlsx_file)

        assert result['mode'] == 'standard_qa'
        assert result['mapping'] == {'title': 0, 'content': 1}
        assert result['confidence'] == 0.95

    def test_standard_question_answer_excel(self, tmp_path):
        xlsx_file = str(tmp_path / 'standard question answer.xlsx')
        _make_xlsx(xlsx_file, ['Question', 'Answer'], [['Q1', 'A1']])

        result = classify_excel_upload(xlsx_file)

        assert result['mode'] == 'standard_qa'
        assert result['mapping'] == {'title': 0, 'content': 1}

    def test_chinese_alias_excel_is_mapped_qa(self, tmp_path):
        xlsx_file = str(tmp_path / 'alias.xlsx')
        _make_xlsx(xlsx_file, ['问题', '答案', '检索词'], [['怎么退货', '进入订单申请退货', '退货|退款']])

        result = classify_excel_upload(xlsx_file)

        assert result['mode'] == 'mapped_qa'
        assert result['mapping']['title'] == 0
        assert result['mapping']['content'] == 1
        assert result['mapping']['indexes'] == 2

    def test_mixed_canonical_and_alias_excel_is_mapped_qa(self, tmp_path):
        xlsx_file = str(tmp_path / 'mixed.xlsx')
        _make_xlsx(xlsx_file, ['title', 'Answer'], [['Q1', 'A1']])

        result = classify_excel_upload(xlsx_file)

        assert result['mode'] == 'mapped_qa'

    def test_unmappable_excel_is_unstructured(self, tmp_path):
        xlsx_file = str(tmp_path / 'fallback.xlsx')
        _make_xlsx(xlsx_file, ['Topic details', 'CAN team answer/feedback'], [['Anti-dumping', 'Answer']])

        result = classify_excel_upload(xlsx_file)

        assert result['mode'] == 'unstructured_excel'
        assert result['mapping'] is None


# ---------------------------------------------------------------------------
# parse_excel_to_json
# ---------------------------------------------------------------------------

class TestParseExcelToJson:
    def test_basic_parse(self, tmp_path):
        xlsx_file = str(tmp_path / 'test.xlsx')
        _make_xlsx(xlsx_file, ['问题', '答案'], [['Q1', 'A1'], ['Q2', 'A2']])
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        assert 'error' not in data
        assert '1' in data
        page = data['1']
        assert page[0]['type'] == 'text'
        assert page[0]['image_path'] is None
        text = page[0]['text_content']
        assert '解析方式: mapped_structured_excel' in text
        assert 'title: Q1' in text
        assert 'content: A1' in text
        assert 'Q1' in text
        assert 'A1' in text

    def test_unmappable_parse_uses_unstructured_fallback(self, tmp_path):
        xlsx_file = str(tmp_path / 'fallback.xlsx')
        _make_xlsx(xlsx_file, ['姓名', '备注'], [['Alice', '普通说明']])
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        text = data['1'][0]['text_content']
        assert '解析方式: unstructured_excel' in text
        assert '姓名: Alice' in text
        assert '备注: 普通说明' in text

    def test_file_with_spaces_in_name(self, tmp_path):
        xlsx_file = str(tmp_path / 'my file with spaces.xlsx')
        _make_xlsx(xlsx_file, ['title', 'content'], [['Hello', 'World']])
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        assert 'error' not in data
        assert 'my file with spaces.xlsx' in data['1'][0]['text_content']

    def test_empty_data_rows(self, tmp_path):
        xlsx_file = str(tmp_path / 'empty.xlsx')
        _make_xlsx(xlsx_file, ['title', 'content'], [])
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        # header-only sheet → one page with header metadata, no error
        assert 'error' not in data

    def test_chunking_splits_pages(self, tmp_path):
        xlsx_file = str(tmp_path / 'large.xlsx')
        rows = [[f'Q{i}', f'A{i}'] for i in range(65)]
        _make_xlsx(xlsx_file, ['title', 'content'], rows)
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path), chunk_size=30))
        # 65 rows / 30 per chunk = 3 chunks
        assert len(data) >= 3

    def test_sheet_name_in_output(self, tmp_path):
        xlsx_file = str(tmp_path / 'sheettest.xlsx')
        wb = Workbook()
        ws = wb.active
        ws.title = 'MySheet'
        ws.append(['title', 'content'])
        ws.append(['T1', 'C1'])
        wb.save(xlsx_file)
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        assert 'MySheet' in data['1'][0]['text_content']

    def test_row_range_in_output(self, tmp_path):
        xlsx_file = str(tmp_path / 'range.xlsx')
        rows = [[f'Q{i}', f'A{i}'] for i in range(5)]
        _make_xlsx(xlsx_file, ['title', 'content'], rows)
        data = json.loads(parse_excel_to_json(xlsx_file, str(tmp_path)))
        text = data['1'][0]['text_content']
        assert '行范围' in text


class TestTransReviewExcelToJsonFile:
    def test_alias_headers_are_canonicalized(self, tmp_path):
        xlsx_file = str(tmp_path / 'alias.xlsx')
        output_file = str(tmp_path / 'out.jsonl')
        _make_xlsx(
            xlsx_file,
            ['问题', '答案', '检索词', '相似问', '补充查询'],
            [['怎么退货', '进入订单申请退货', '退货|退款', '如何退货|退货流程', '订单售后|退货入口']],
        )

        trans_review_excel_to_json_file(
            xlsx_file,
            output_file,
            list_field_names='synonyms_title,supply_info_query',
        )

        with open(output_file, 'r', encoding='utf-8') as f:
            row = json.loads(f.readline())

        assert row['title'] == '怎么退货'
        assert row['content'] == '进入订单申请退货'
        assert row['indexes'] == [{'text': '退货'}, {'text': '退款'}]
        assert row['synonyms_title'] == ['如何退货', '退货流程']
        assert row['supply_info_query'] == ['订单售后', '退货入口']


class TestTransWebExcelToJsonFile:
    def test_alias_headers_are_canonicalized_with_extra_fields(self, tmp_path):
        xlsx_file = str(tmp_path / 'web alias with spaces.xlsx')
        output_file = str(tmp_path / 'web out.jsonl')
        _make_xlsx(
            xlsx_file,
            ['问题', '答案', '检索词'],
            [['怎么退货', '进入订单申请退货', '退货|退款']],
        )

        trans_web_excel_to_json_file(
            xlsx_file,
            output_file,
            extra_field_name_dict={'task_id': 'task-1', 'audit_result': 1},
        )

        with open(output_file, 'r', encoding='utf-8') as f:
            row = json.loads(f.readline())

        assert row['title'] == '怎么退货'
        assert row['content'] == '进入订单申请退货'
        assert row['indexes'] == [{'text': '退货'}, {'text': '退款'}]
        assert row['task_id'] == 'task-1'
        assert row['audit_result'] == 1
        assert row['multimodal_contents'] == [{'type': 'text', 'content': '进入订单申请退货'}]


if __name__ == '__main__':
    pytest.main([__legacy_source_file__, '-v'])
