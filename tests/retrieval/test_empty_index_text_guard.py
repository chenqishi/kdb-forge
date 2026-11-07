# -*- coding: utf-8 -*-
"""空 index text 的三层防护回归。

实测：模型输出「[phrases]:」后面空着时 ''.split(',') 得到 ['']，一路带到 indexes 就是空 text，
送 DashScope embedding 直接 400，异常上抛让**整条 segment** 入库失败。
wayfair 任务 74256b78 的 772 条待插入段落里有 21 条中招。
"""

import pytest


class TestSchemaTransFiltersBlankIndexTerms:
    """第二层：构造 indexes 时逐项滤空（列表非空 ≠ 元素非空）。"""

    def _build(self, **kw):
        from kdb.mining.transformations.schema_trans import trans_doc_segment_to_search_data
        info = {'keywords': ['报告'], 'phrases': [], 'topics': [],
                'content': {'1': [{'type': 'text', 'text_content': '正文'}]},
                'from_file_name': 'x.docx', 'index_file_name': 'x', 'pages': [1, 1]}
        info.update(kw)
        return trans_doc_segment_to_search_data(info, None, None, 'tid', None)

    def test_blank_phrase_element_is_dropped(self):
        data = self._build(phrases=[''])
        assert all(str(i['text']).strip() for i in data['indexes'])

    def test_blank_topic_element_is_dropped(self):
        data = self._build(topics=['', '  ', '怎么导出？'])
        texts = [i['text'] for i in data['indexes']]
        assert '怎么导出？' in texts
        assert all(str(t).strip() for t in texts)

    def test_all_blank_keywords_produce_no_joined_entry(self):
        data = self._build(keywords=['', ' '])
        assert all(str(i['text']).strip() for i in data['indexes'])

    def test_real_terms_survive(self):
        data = self._build(keywords=['报告', '流量'], phrases=['怎么导表'], topics=['在哪下载？'])
        texts = [i['text'] for i in data['indexes']]
        assert '报告,流量' in texts and '怎么导表' in texts and '在哪下载？' in texts


class TestParseIndexAnswerFiltersBlanks:
    """第一层：解析模型回答时就滤掉空白项。"""

    def test_empty_phrases_line_yields_no_blank_entry(self):
        builder = pytest.importorskip(
            'kdb.mining.generation.builders.knowlege_segment_builder_by_dify',
            reason='需要 knowledge_clear_tool 等运行时依赖，缺失时跳过')
        answer = '[keywords]: 报告,流量\n[phrases]:\n[topic]: 怎么导出？'
        info = builder.parse_index_answer(answer, 'x.docx', [1, 1],
                                          {'1': [{'type': 'text', 'text_content': '正文'}]})
        assert info['phrases'] == []
        assert all(str(t).strip() for t in info['keywords'] + info['topics'])
