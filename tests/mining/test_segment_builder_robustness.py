# -*- coding: utf-8 -*-
"""段落生成的健壮性回归：空段落不请求 Dify、单段/单文件失败不打死整批。

对应两次真实事故（wayfair 任务 74256b78）：
  - 2026-03 `KeyError: '8'` 在第 21 个文件处让整批退出
  - 2026-09 `ValueError: inputs is empt`（只有图片的空页）在第 7 个文件处让整批退出
两次都导致 235 个文件一条 segment 都没产出。
"""

import json
import sys
import types

import pytest


def _stub_deps():
    """段落生成依赖 dify/config/knowledge_clear_tool，单测里全部打桩。"""
    if 'kdb.mining.common.generation.segments' in sys.modules:
        return


_stub_deps()
pytest.importorskip('fire')

builder = pytest.importorskip(
    'kdb.mining.common.generation.segments',
    reason='需要 knowledge_clear_tool 等运行时依赖，缺失时跳过',
)


class _Dify:
    """记录被请求的内容；对空输入按真实实现抛 ValueError。"""

    def __init__(self, answer='[keywords]: 报告\n[topic]: 怎么下载报告？'):
        self.answer = answer
        self.calls = []

    def request_dify(self, paragraph, *a, **k):
        self.calls.append(paragraph)
        if not paragraph:
            raise ValueError('inputs is empt, paragraph: %s' % paragraph)
        return self.answer


def _doc(pages):
    """pages: {页码: 文本}；空文本表示只有图片的页。"""
    return {str(k): [{'type': 'text', 'text_content': v, 'image_path': None}]
            for k, v in pages.items()}


class TestEmptySegmentNotSentToDify:
    def test_image_only_page_is_skipped(self, tmp_path, monkeypatch):
        data = _doc({1: '正文' * 1200, 2: '', 3: '结尾' * 1200})
        path = tmp_path / 'c.json'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        seg, idx = _Dify('[段落]\n标题: 全文\n页码: 1-3'), _Dify()
        builder.get_segment_knowledge_by_dify(str(path), seg, idx, from_file_name='x.docx')
        assert all(c and c.strip() for c in idx.calls), '空内容不能送进 dify_index'

    def test_all_empty_document_returns_empty_not_raise(self, tmp_path):
        data = _doc({1: '', 2: ''})
        path = tmp_path / 'c.json'
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        seg, idx = _Dify(), _Dify()
        assert builder.get_segment_knowledge_by_dify(str(path), seg, idx, from_file_name='x.docx') == []
        assert idx.calls == []


class TestBatchIsolatesFileFailure:
    def test_one_bad_file_does_not_kill_the_batch(self, tmp_path, monkeypatch, capsys):
        good = tmp_path / 'good.json'
        good.write_text(json.dumps(_doc({1: '正文'}), ensure_ascii=False), encoding='utf-8')
        batch = tmp_path / 'batch.txt'
        batch.write_text(
            f'wayfair\tbad.docx\tdocx\t/x\t/x\t/x\t{tmp_path}/missing.json\n'
            f'wayfair\tgood.docx\tdocx\t/x\t/x\t/x\t{good}\n', encoding='utf-8')

        calls = []

        def fake(pdf_json_file, *a, **k):
            calls.append(pdf_json_file)
            if 'missing' in pdf_json_file:
                raise KeyError('8')          # 复刻 2026-03 的崩溃
            return [{'keywords': [], 'phrases': [], 'topics': [], 'content': {},
                     'from_file_name': 'good.docx', 'index_file_name': 'good', 'pages': [1, 1]}]

        monkeypatch.setattr(builder, 'get_segment_knowledge_by_dify', fake)
        monkeypatch.setattr(builder, 'DifyWorkFlowRequest', lambda **kw: _Dify())
        builder.run_batch_get_segment_knowledge(str(batch), 'flag', 1, 0, 1, 0)

        assert len(calls) == 2, '第一个文件抛异常后必须继续处理第二个'
        assert 'good.docx' in capsys.readouterr().out


class TestNonContiguousPages:
    """页码不连续：既无文字也无图片的空白页会被解析丢掉。

    实测 `欧盟 _ 英国阻燃要求.docx` 是 100 页但最大页号 113、中间缺 13 页，
    旧实现按 len(dict) 当上界并直接下标取值，抛 KeyError: '8' 打死整批。
    """

    def _doc_with_gaps(self):
        # 页 1,2,3,5,6,7,9 —— 缺 4 和 8
        return {str(p): [{'type': 'text', 'text_content': f'第{p}页正文', 'image_path': None}]
                for p in (1, 2, 3, 5, 6, 7, 9)}

    def test_missing_page_is_skipped_not_raising(self):
        data = self._doc_with_gaps()
        info = builder.parse_index_answer('[keywords]: a\n[topic]: 怎么办？', 'x.docx', [7, 8], data)
        assert set(info['content']) <= set(data)
        assert '8' not in info['content']

    def test_still_returns_surrounding_pages(self):
        data = self._doc_with_gaps()
        info = builder.parse_index_answer('[keywords]: a\n[topic]: 怎么办？', 'x.docx', [6, 7], data)
        # 前面多取一页（5），缺失页不报错，正常页都在
        assert sorted(info['content'], key=int) == ['5', '6', '7']

    def test_prior_page_falls_back_to_nearest_existing(self):
        """缺口多时，前一页号常正好落在缺口上，要退到最近的已存在前页。"""
        data = self._doc_with_gaps()          # 缺 4 和 8
        info = builder.parse_index_answer('[keywords]: a\n[topic]: 怎么办？', 'x.docx', [9, 9], data)
        assert sorted(info['content'], key=int) == ['7', '9']   # 前一页 8 不存在 -> 退到 7

    def test_pages_beyond_max_are_clamped(self):
        data = self._doc_with_gaps()
        info = builder.parse_index_answer('[keywords]: a\n[topic]: 怎么办？', 'x.docx', [9, 99], data)
        assert sorted(info['content'], key=int) == ['7', '9']   # 上界被钳到最大页号 9

    def test_page_count_smaller_than_max_page_number(self):
        """7 页但最大页号 9：旧实现用 len(dict) 当上界会漏掉真实存在的第 9 页。"""
        data = self._doc_with_gaps()
        info = builder.parse_index_answer('[keywords]: a\n[topic]: 怎么办？', 'x.docx', [9, 9], data)
        assert '9' in info['content']


class TestShortDocumentBranchGuards:
    """短文档分支（整篇 <2000 字符）一直缺 answer 判空，长文档分支早就有。

    实测 `基础运营_供应商账户详情页面.docx` 因 Dify 返回 None 抛
    AttributeError: 'NoneType' object has no attribute 'replace'。
    """

    def _short_doc(self, tmp_path):
        data = {'1': [{'type': 'text', 'text_content': '短正文', 'image_path': None}]}
        p = tmp_path / 'short.json'
        p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return str(p)

    def test_none_answer_returns_empty_not_raise(self, tmp_path):
        class _NoneDify:
            def request_dify(self, *a, **k):
                return None
        assert builder.get_segment_knowledge_by_dify(
            self._short_doc(tmp_path), _NoneDify(), _NoneDify(), from_file_name='x.docx') == []

    def test_request_exception_returns_empty_not_raise(self, tmp_path):
        class _BoomDify:
            def request_dify(self, *a, **k):
                raise RuntimeError('dify down')
        assert builder.get_segment_knowledge_by_dify(
            self._short_doc(tmp_path), _BoomDify(), _BoomDify(), from_file_name='x.docx') == []
