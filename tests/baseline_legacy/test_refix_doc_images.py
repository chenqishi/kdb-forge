# -*- coding: utf-8 -*-
"""refix_doc_images 的离线单测：只测 md5 对齐与字段贴回，不解析 PDF、不打网络。"""

import hashlib
import json
import sys
import types

import pytest


def _stub_wordtotext():
    """parse_pdf_to_json 依赖 fitz/LibreOffice，单测里不需要，打桩掉。"""
    if 'knowledge_clear_tool.wordtotext' in sys.modules:
        return
    pkg = sys.modules.setdefault('knowledge_clear_tool', types.ModuleType('knowledge_clear_tool'))
    pkg.__path__ = []
    mod = types.ModuleType('knowledge_clear_tool.wordtotext')
    mod.convert_docx_to_pdf = lambda *a, **k: None
    mod.parse_pdf_to_json = lambda *a, **k: '{}'
    sys.modules['knowledge_clear_tool.wordtotext'] = mod


_stub_wordtotext()
from data_control_tools.refix_doc_images import build_image_md5_map, remap_parsed_images  # noqa: E402


@pytest.fixture
def img(tmp_path):
    def _make(name, payload):
        p = tmp_path / name
        p.write_bytes(payload)
        return str(p)
    return _make


def _entry(path, url, understanding='看图说话'):
    return {'type': 'image', 'image_path': path, 'public_url': url, 's3_path': url.split('/')[-1],
            'image_understanding': understanding, 'image_ocr': 'OCR', 'is_valid': 'True',
            'is_valid_by_img_info': 'True', 'is_valid_by_ocr': 'True', 'fileName': 'old.jpeg',
            'text_content': None, 'extern_url': None}


class TestBuildImageMd5Map:
    def test_keys_by_content_not_path(self, tmp_path, img):
        a, b = img('1_0.jpeg', b'AAA'), img('5_0.jpeg', b'AAA')   # 同内容不同页
        info = {'u1': _entry(a, 'https://x/1.jpeg'), 'u2': _entry(b, 'https://x/1.jpeg')}
        p = tmp_path / 'mm.json'
        p.write_text(json.dumps(info), encoding='utf-8')
        m = build_image_md5_map(str(p))
        assert list(m) == [hashlib.md5(b'AAA').hexdigest()]

    def test_skips_missing_local_file(self, tmp_path):
        info = {'u1': _entry('/nope/gone.jpeg', 'https://x/1.jpeg')}
        p = tmp_path / 'mm.json'
        p.write_text(json.dumps(info), encoding='utf-8')
        assert build_image_md5_map(str(p)) == {}


class TestRemapParsedImages:
    def test_reuses_understanding_and_keeps_new_page_placement(self, tmp_path, img):
        old_path = img('old_1_0.jpeg', b'PNGDATA')
        md5_map = {hashlib.md5(b'PNGDATA').hexdigest(): _entry(old_path, 'https://x/a.jpeg')}
        new_path = img('7_1.jpeg', b'PNGDATA')          # 同内容，重解析后落在第7页
        parsed = {'7': [{'type': 'image', 'image_path': new_path, 'text_content': None}]}
        fixed, stats = remap_parsed_images(parsed, md5_map)
        item = fixed['7'][0]
        assert stats == {'images': 1, 'matched': 1, 'matched_no_mm': 0,
                         'missed': 0, 'missed_files': []}
        assert item['image_understanding'] == '看图说话'
        assert item['public_url'] == 'https://x/a.jpeg'
        assert item['image_path'] == new_path           # 用新路径，不是旧的
        assert item['fileName'] == '7_1.jpeg'

    def test_unmatched_image_is_kept_not_dropped(self, tmp_path, img):
        parsed = {'1': [{'type': 'image', 'image_path': img('1_0.jpeg', b'NEW'), 'text_content': None}]}
        fixed, stats = remap_parsed_images(parsed, {})
        assert stats['matched'] == 0 and stats['missed'] == 1
        assert len(fixed['1']) == 1                     # 不丢图
        assert fixed['1'][0]['public_url'] is None
        assert fixed['1'][0]['is_valid'] == 'False'

    def test_text_items_pass_through_with_null_image_fields(self):
        parsed = {'1': [{'type': 'text', 'text_content': '正文', 'image_path': None}]}
        fixed, stats = remap_parsed_images(parsed, {})
        assert stats['images'] == 0
        assert fixed['1'][0]['text_content'] == '正文'
        assert fixed['1'][0]['public_url'] is None and fixed['1'][0]['is_valid'] == 'False'

    def test_duplicated_source_page_collapses_to_real_placement(self, tmp_path, img):
        """旧解析每页都挂全部图；重解析后只在真实页出现一次。"""
        a = img('a.jpeg', b'A'); b = img('b.jpeg', b'B')
        md5_map = {hashlib.md5(b'A').hexdigest(): _entry(a, 'https://x/a.jpeg'),
                   hashlib.md5(b'B').hexdigest(): _entry(b, 'https://x/b.jpeg')}
        parsed = {'1': [{'type': 'image', 'image_path': a, 'text_content': None}],
                  '2': [{'type': 'image', 'image_path': b, 'text_content': None}]}
        fixed, stats = remap_parsed_images(parsed, md5_map)
        assert stats['images'] == 2 and stats['matched'] == 2
        assert fixed['1'][0]['public_url'] == 'https://x/a.jpeg'
        assert fixed['2'][0]['public_url'] == 'https://x/b.jpeg'


class TestFileLevelMapAndStats:
    """按单文件旧解析对齐，并把「本来就没多模态结果」与「真未命中」分开。"""

    def test_build_file_md5_map_includes_images_without_public_url(self, tmp_path, img):
        from data_control_tools.refix_doc_images import build_file_md5_map
        p = img('1_0.jpeg', b'LOGO')
        old = {'1': [{'type': 'image', 'image_path': p, 'public_url': None, 'is_valid': 'False'}]}
        m = build_file_md5_map(old)
        assert hashlib.md5(b'LOGO').hexdigest() in m      # 全局表不会收录它，单文件表必须收录

    def test_image_without_multimodal_counted_separately(self, tmp_path, img):
        from data_control_tools.refix_doc_images import build_file_md5_map
        old_p = img('old_1_0.jpeg', b'LOGO')
        old = {'1': [{'type': 'image', 'image_path': old_p, 'public_url': None, 'is_valid': 'False'}]}
        new_p = img('3_0.jpeg', b'LOGO')
        parsed = {'3': [{'type': 'image', 'image_path': new_p, 'text_content': None}]}
        _, stats = remap_parsed_images(parsed, build_file_md5_map(old))
        assert stats['matched'] == 0 and stats['matched_no_mm'] == 1 and stats['missed'] == 0

    def test_image_with_multimodal_counted_as_matched(self, tmp_path, img):
        from data_control_tools.refix_doc_images import build_file_md5_map
        old_p = img('old_2_0.jpeg', b'SHOT')
        old = {'2': [_entry(old_p, 'https://x/s.jpeg')]}
        new_p = img('5_0.jpeg', b'SHOT')
        parsed = {'5': [{'type': 'image', 'image_path': new_p, 'text_content': None}]}
        fixed, stats = remap_parsed_images(parsed, build_file_md5_map(old))
        assert stats['matched'] == 1 and stats['matched_no_mm'] == 0
        assert fixed['5'][0]['public_url'] == 'https://x/s.jpeg'


class TestTextSameRelaxation:
    """旧解析的零文本页被丢掉不算分页变化；真丢了正文才算。"""

    def test_page_text_helper(self):
        from data_control_tools.refix_doc_images import _page_text
        assert _page_text([{'text_content': 'a'}, {'text_content': None}, {'text_content': 'b'}]) == 'ab'

    def test_dropped_empty_last_page_is_acceptable(self):
        from data_control_tools.refix_doc_images import _page_text
        old = {'1': [{'text_content': '正文'}], '2': [{'text_content': ''}]}
        new = {'1': [{'text_content': '正文'}]}
        dropped = sorted(set(old) - set(new), key=int)
        had_text = [p for p in dropped if _page_text(old[p]).strip()]
        assert dropped == ['2'] and had_text == []

    def test_dropped_page_with_text_is_rejected(self):
        from data_control_tools.refix_doc_images import _page_text
        old = {'1': [{'text_content': '正文'}], '2': [{'text_content': '重要内容'}]}
        new = {'1': [{'text_content': '正文'}]}
        dropped = sorted(set(old) - set(new), key=int)
        assert [p for p in dropped if _page_text(old[p]).strip()] == ['2']
