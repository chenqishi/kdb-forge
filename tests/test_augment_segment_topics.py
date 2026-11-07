# -*- coding: utf-8 -*-
"""augment_segment_topics 的离线单测：只测解析与去重，不打网络。"""

import sys
import types

import pytest


def _stub():
    """embedding / LLM 后端在单测里不需要，打桩掉。"""
    if 'commons.embedding_tools' not in sys.modules:
        m = types.ModuleType('commons.embedding_tools')
        m.AliEmbedding = lambda *a, **k: None
        sys.modules['commons.embedding_tools'] = m
    if 'commons.local_llm_adapter' not in sys.modules:
        m = types.ModuleType('commons.local_llm_adapter')
        m.request_knowledge_llm = lambda *a, **k: ''
        sys.modules['commons.local_llm_adapter'] = m


_stub()
from data_control_tools import augment_segment_topics as aug  # noqa: E402

BODY = '报告中心可以下载账户概览、选项钻取、详细列表健康等报告，含曝光量与会话量。' * 3


def _answer(*lines):
    return '\n'.join(lines)


@pytest.fixture
def llm(monkeypatch):
    def _set(text):
        monkeypatch.setattr(aug, 'request_knowledge_llm', lambda *a, **k: text)
    return _set


class TestGenerateSimilarTopics:
    def test_parses_lines_and_strips_numbering(self, llm):
        llm(_answer('1. 链接流量数据怎么导出？', '2、后台报表在哪下载？', '- 怎么看单个链接的曝光？'))
        got = aug.generate_similar_topics(BODY, [])
        # 解析出的原句在前，术语变体追加在后
        assert got[:3] == ['链接流量数据怎么导出？', '后台报表在哪下载？', '怎么看单个链接的曝光？']

    def test_drops_duplicates_of_existing(self, llm):
        llm(_answer('如何下载报告中心的报告？', '链接流量数据怎么导出？'))
        got = aug.generate_similar_topics(BODY, ['如何下载报告中心的报告？'])
        assert got[:1] == ['链接流量数据怎么导出？']
        assert '如何下载报告中心的报告？' not in got

    def test_dedupes_within_answer_ignoring_punctuation(self, llm):
        llm(_answer('链接流量怎么导出', '链接流量怎么导出？', '链接流量怎么导出。'))
        # 三条只算一条；后面追加的是正文指标推出来的问法，不算模型产出
        assert aug.generate_similar_topics(BODY, [])[:1] == ['链接流量怎么导出']

    def test_drops_too_short_and_too_long(self, llm):
        llm(_answer('啊？', '流量' * 40, '产品链接的流量数据在哪导出？'))
        assert aug.generate_similar_topics(BODY, [])[:1] == ['产品链接的流量数据在哪导出？']

    def test_respects_count_cap(self, llm):
        llm(_answer(*[f'第{i}种问法怎么导出流量数据？' for i in range(20)]))
        # count 只约束模型产出条数；术语变体是额外追加的
        got = aug.generate_similar_topics(BODY, [], count=6)
        assert len([t for t in got if t.startswith('第')]) == 6

    def test_empty_model_output_returns_empty(self, llm):
        llm('')
        assert aug.generate_similar_topics(BODY, []) == []

    def test_llm_exception_does_not_propagate(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('backend down')
        monkeypatch.setattr(aug, 'request_knowledge_llm', boom)
        assert aug.generate_similar_topics(BODY, []) == []

    def test_empty_content_skips_llm_call(self, monkeypatch):
        called = []
        monkeypatch.setattr(aug, 'request_knowledge_llm',
                            lambda *a, **k: called.append(1) or '问法？')
        assert aug.generate_similar_topics('[multimodal_prefix]abc\nhttps://x/y.jpg', []) == []
        assert not called


class TestCleanContent:
    def test_strips_image_placeholders_and_page_markers(self):
        raw = '第1页内容如下：正文A\n[multimodal_prefix]kg/x.jpeg\nhttps://file/y.jpeg\n第2页内容如下:正文B'
        assert aug._clean_content(raw) == '正文A\n正文B'


class TestExpandTermVariants:
    """模型即便给了对照表也常照抄文档词，靠确定性替换补上卖家说法。

    实测「列表的流量数据在哪看？」对 query「如何导出链接流量数据」只有 0.710，
    换成「链接的流量数据怎么导出？」是 0.987。
    """

    def test_combined_noun_and_verb_swap_comes_first(self):
        got = aug.expand_term_variants(['列表的流量数据在哪看？'])
        assert got[0] == '链接的流量数据怎么导出？'

    def test_longer_term_wins_over_its_prefix(self):
        """会话 ⊂ 会话量：不能产出「流量量」这种残句。"""
        got = aug.expand_term_variants(['会话量怎么统计？'])
        assert all('流量量' not in x for x in got)
        assert '流量怎么导出？' in got

    def test_strips_parenthetical_official_term(self):
        got = aug.expand_term_variants(['赞助产品曝光量（曝光）怎么导出？'])
        assert '赞助产品曝光量怎么导出？' in got

    def test_no_variant_when_nothing_matches(self):
        assert aug.expand_term_variants(['报告中心能看销售数据吗？']) == []

    def test_does_not_repeat_existing_or_source(self):
        got = aug.expand_term_variants(['列表的流量数据在哪看？'],
                                       existing_texts=['链接的流量数据怎么导出？'])
        assert '链接的流量数据怎么导出？' not in got

    def test_respects_per_topic_cap(self):
        got = aug.expand_term_variants(['列表的会话量在哪看？'], max_variants_per_topic=2)
        assert len(got) == 2

    def test_generate_similar_topics_appends_variants(self, llm):
        llm('列表的流量数据在哪看？')
        got = aug.generate_similar_topics(BODY, [])
        assert '列表的流量数据在哪看？' in got            # 原句保留
        assert '链接的流量数据怎么导出？' in got          # 变体补上


class TestObjectMetricTopics:
    """文档写指标术语，卖家写"对象+口语指标+动作"，两者之间光靠替换跨不过去。

    实测：「会话量怎么统计计算？」对 query「如何导出链接流量数据」只有 0.539，
    补成「链接的流量数据怎么导出？」是 0.987。
    """

    TRAFFIC = ('● 会话量：访问期间看过供应商产品的客户数。● 转化率：导致下单的会话百分比。'
               '● 赞助产品曝光量：产品出现在赞助位的次数。')

    def test_emits_object_plus_seller_metric_plus_action(self):
        got = aug.build_object_metric_topics(self.TRAFFIC, [])
        assert '链接的流量数据怎么导出？' in got
        assert '产品链接的曝光数据怎么导出？' in got

    def test_no_topics_when_segment_has_no_metrics(self):
        assert aug.build_object_metric_topics('退货详情：采购订单号、供应商零件ID、退货原因。', []) == []

    def test_every_metric_gets_export_form_before_doubling_actions(self):
        got = aug.build_object_metric_topics(self.TRAFFIC, [], max_topics=8)
        assert all(t.endswith('怎么导出？') for t in got)      # 上限内先铺满"导出"
        assert len({t for t in got if '曝光' in t}) and len({t for t in got if '流量' in t})

    def test_longer_metric_wins_over_prefix(self):
        """命中"总曝光量"后不该再按"曝光量"重复产一遍。"""
        got = aug.build_object_metric_topics('总曝光量：SKU 被加载的次数。', [])
        assert '链接的曝光数据怎么导出？' in got
        assert len(got) == len(set(got))

    def test_respects_existing_texts(self):
        got = aug.build_object_metric_topics(self.TRAFFIC, ['链接的流量数据怎么导出？'])
        assert '链接的流量数据怎么导出？' not in got

    def test_caps_total(self):
        assert len(aug.build_object_metric_topics(self.TRAFFIC, [], max_topics=3)) == 3


class TestNameFilter:
    """only_files 清单用于并行分片。"""

    def test_reads_list_file(self, tmp_path):
        p = tmp_path / 'names.txt'
        p.write_text('a.docx\n\nb.docx\n', encoding='utf-8')
        assert aug._load_name_filter(None, str(p)) == {'a.docx', 'b.docx'}

    def test_merges_single_and_list(self, tmp_path):
        p = tmp_path / 'names.txt'
        p.write_text('b.docx\n', encoding='utf-8')
        assert aug._load_name_filter('a.docx', str(p)) == {'a.docx', 'b.docx'}

    def test_none_when_no_filter(self):
        assert aug._load_name_filter(None, None) is None


def test_verb_swap_does_not_truncate_longer_pattern():
    """'在哪里查询' 不能被短模式 '在哪里查' 切成 '怎么导出询'。"""
    from data_control_tools.augment_segment_topics import _verb_swaps
    out = _verb_swaps('B2B会话量在哪里查询？')
    assert out, '应当产出变体'
    assert all('询' not in t for t in out), out
    assert 'B2B会话量怎么导出？' in out


def test_verb_swap_matches_only_one_pattern():
    """一句只按最长的那个动词模式换一次，不叠加短模式的产物。"""
    from data_control_tools.augment_segment_topics import _verb_swaps
    assert _verb_swaps('会话量在哪看？') == ['会话量怎么导出？', '会话量怎么下载？']


def test_verb_swap_no_match_returns_empty():
    from data_control_tools.augment_segment_topics import _verb_swaps
    assert _verb_swaps('这句话里没有动词模式') == []
