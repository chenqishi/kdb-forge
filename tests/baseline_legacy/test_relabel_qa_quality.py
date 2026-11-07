# -*- coding: utf-8 -*-
"""
存量 QA 质量重打标的行为测试（全部用假 LLM / 假 ES，不打真实接口）。

重点是三条不能错的语义：
  1. 判不出来（对不上 / 少回条 / 正文含协议分隔符）→ **保持原档位**，不能像生产流程那样降 mid
  2. `优质` 与降级标签同时出现 → 判 low（judge_qa_quality 默认是 HIGH 优先，对重打标是危险默认值）
  3. 只对档位真正变化的文档发写请求；dry-run 不产生任何写请求
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_relabel_qa_quality.py')
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.insert(0, ROOT)

from chat_qa_extract import quality_filter  # noqa: E402
from data_control_tools import relabel_qa_quality_by_llm as relabel  # noqa: E402


def _docs(n, level='high'):
    return [{'_id': f'id{i}', 'q': f'第{i}个问题是什么？', 'a': f'第{i}个答案。',
             'old_level': level} for i in range(1, n + 1)]


def _reply(n, tags_by_index=None):
    """造一份与 _docs(n) 对齐的质检返回，tags_by_index: {序号: '#优质'}"""
    tags_by_index = tags_by_index or {}
    return '\n###\n'.join(
        f'{i}.问题:第{i}个问题是什么？\n答案:第{i}个答案。{tags_by_index.get(i, "")}'
        for i in range(1, n + 1))


class _FakeFilter:
    """只按预设脚本回内容的假质检器，接口与 QaQualityFilter 兼容"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_dify(self, paragraph, other_inputs=None):
        self.calls.append(paragraph)
        return self.responses.pop(0) if self.responses else None


# --- 标签 → 档位 ----------------------------------------------------------

@pytest.mark.parametrize('tags,expected', [
    (['优质'], 'high'),
    (['不通用'], 'low'),
    (['无实质答案'], 'low'),
    (['不相关'], 'low'),
    (['不清晰'], 'mid'),
    (['需要修改'], 'mid'),
    ([], 'mid'),
])
def test_judge_level_strict_matches_production_mapping(tags, expected):
    assert relabel.judge_level_strict(tags) == expected


def test_low_tag_beats_high_tag():
    """模型偶尔两个都写；HIGH 优先会让重打标等于没改，必须按降级处理"""
    assert relabel.judge_level_strict(['优质', '不通用']) == 'low'
    assert relabel.judge_level_strict(['优质', '无实质答案']) == 'low'


# --- 正常打标 -------------------------------------------------------------

def test_relabel_chunk_maps_tags_to_ids_in_order():
    docs = _docs(3)
    fake = _FakeFilter([_reply(3, {1: '#优质', 2: '#不通用', 3: '#不清晰'})])
    results = relabel.relabel_chunk(docs, fake)

    assert [r['_id'] for r in results] == ['id1', 'id2', 'id3']
    assert [r['new_level'] for r in results] == ['high', 'low', 'mid']
    assert all(r['aligned'] for r in results)


def test_chunk_input_uses_indexed_qa_format():
    """送模型的文本必须是 qajson_to_line_text(add_index=True) 的格式，否则解析对不上"""
    fake = _FakeFilter([_reply(2)])
    relabel.relabel_chunk(_docs(2), fake)
    assert fake.calls[0].startswith('1.问题:')
    assert '\n###\n' in fake.calls[0]


# --- 判不出来必须保持原档位 -----------------------------------------------

def test_missing_row_keeps_original_level():
    """模型少回一条 → 缺失那条保持 high，不降 mid"""
    docs = _docs(3)
    fake = _FakeFilter([_reply(2, {1: '#不通用', 2: '#不通用'})])
    results = relabel.relabel_chunk(docs, fake)

    assert results[2]['new_level'] == 'high'
    assert results[2]['aligned'] is False
    assert results[2]['skip_reason'] == 'missing_in_result'


def test_text_mismatch_keeps_original_level():
    """返回的文本对不上（错位）→ 保持原档位并记 text_mismatch"""
    docs = _docs(2)
    mismatched = ('1.问题:完全不相干的问题内容XYZ\n答案:完全不相干的答案内容XYZ#不通用'
                  '\n###\n2.问题:第2个问题是什么？\n答案:第2个答案。#不通用')
    results = relabel.relabel_chunk(docs, _FakeFilter([mismatched]))

    assert results[0]['new_level'] == 'high'
    assert results[0]['skip_reason'] == 'text_mismatch'
    assert results[1]['new_level'] == 'low'


def test_untagged_row_keeps_original_level():
    """
    无标签 ≠ mid。QaQualityFilter 对齐失败时整批退化成「原文无标签」，
    如果把它当成「模型判成 mid」，一批 40 条 high 会被静默降级——这是必须堵死的。
    """
    docs = _docs(3)
    results = relabel.relabel_chunk(docs, _FakeFilter([_reply(3)]))

    assert [r['new_level'] for r in results] == ['high'] * 3
    assert {r['skip_reason'] for r in results} == {'no_tag'}
    assert not any(r['aligned'] for r in results)


def test_empty_llm_result_keeps_all_levels():
    results = relabel.relabel_chunk(_docs(3), _FakeFilter([None]))
    assert [r['new_level'] for r in results] == ['high'] * 3
    assert {r['skip_reason'] for r in results} == {'empty_llm_result'}


# --- 协议分隔符 -----------------------------------------------------------

@pytest.mark.parametrize('field,value', [
    ('a', '步骤如下：\n### 第一步\n打开后台'),
    ('q', '问题:这算什么'),
    ('a', '答案：见上'),
])
def test_protocol_markers_are_detected(field, value):
    doc = {'_id': 'x', 'q': '正常问题', 'a': '正常答案', 'old_level': 'high'}
    doc[field] = value
    assert relabel.is_protocol_safe(doc) is False


def test_normal_doc_is_protocol_safe():
    assert relabel.is_protocol_safe({'q': '可以用大陆主体入驻吗？', 'a': '可以'}) is True


# --- 分块缓存 -------------------------------------------------------------

def test_chunk_cache_is_reused_when_ids_match(tmp_path):
    chunk = _docs(2)
    cached = [{'_id': 'id1', 'old_level': 'high', 'new_level': 'low', 'tags': ['不通用'],
               'aligned': True, 'skip_reason': ''},
              {'_id': 'id2', 'old_level': 'high', 'new_level': 'high', 'tags': ['优质'],
               'aligned': True, 'skip_reason': ''}]
    f = tmp_path / 'chunk_00000.json'
    f.write_text(json.dumps(cached), encoding='utf-8')

    assert relabel._load_chunk_cache(str(f), chunk) == cached


def test_chunk_cache_is_rejected_when_ids_differ(tmp_path):
    """
    缓存文件名只带块序号；改了 batch_size 重跑时同序号对应的是别的 QA。
    不校验就会张冠李戴——实测把 6312 条跑成 9323 条。
    """
    f = tmp_path / 'chunk_00000.json'
    f.write_text(json.dumps([{'_id': 'other1'}, {'_id': 'other2'}]), encoding='utf-8')

    assert relabel._load_chunk_cache(str(f), _docs(2)) is None


def test_chunk_cache_missing_or_corrupt_returns_none(tmp_path):
    assert relabel._load_chunk_cache(str(tmp_path / 'nope.json'), _docs(1)) is None
    bad = tmp_path / 'bad.json'
    bad.write_text('{not json', encoding='utf-8')
    assert relabel._load_chunk_cache(str(bad), _docs(1)) is None


# --- 写回 -----------------------------------------------------------------

class _FakeEs:
    def __init__(self):
        self.bulk_calls = []

    def bulk_update_field(self, index, updates, field, batch_size=200):
        self.bulk_calls.append({'index': index, 'updates': updates, 'field': field})
        return {'updated': len(updates), 'failed': []}


def test_only_changed_docs_are_written(tmp_path):
    decisions = [
        {'_id': 'a', 'old_level': 'high', 'new_level': 'low', 'tags': ['不通用'], 'aligned': True},
        {'_id': 'b', 'old_level': 'high', 'new_level': 'high', 'tags': ['优质'], 'aligned': True},
        {'_id': 'c', 'old_level': 'high', 'new_level': 'mid', 'tags': ['不清晰'], 'aligned': True},
    ]
    es = _FakeEs()
    rollback_file = str(tmp_path / 'rollback.jsonl')
    result = relabel.apply_updates(es, 'idx', decisions, rollback_file)

    assert result['updated'] == 2
    assert es.bulk_calls[0]['field'] == 'quality_level'
    assert sorted(es.bulk_calls[0]['updates']) == [('a', 'low'), ('c', 'mid')]

    rows = [json.loads(l) for l in open(rollback_file, encoding='utf-8')]
    assert sorted((r['_id'], r['quality_level']) for r in rows) == [('a', 'high'), ('c', 'high')]


def test_no_change_means_no_write(tmp_path):
    decisions = [{'_id': 'a', 'old_level': 'high', 'new_level': 'high',
                  'tags': ['优质'], 'aligned': True}]
    es = _FakeEs()
    result = relabel.apply_updates(es, 'idx', decisions, str(tmp_path / 'rollback.jsonl'))
    assert result['updated'] == 0
    assert es.bulk_calls == []


# --- 查询构造 -------------------------------------------------------------

def test_query_filters_by_from_type_not_from_type_norm():
    """`自动学习` 是历史写法，按 from_type_norm 过滤会漏掉存量"""
    query = relabel.build_target_query(from_type='chat_auto', data_type='qa',
                                       quality_level='high')
    fields = [list(f['term'].keys())[0] for f in query['bool']['filter']]
    assert 'from_type' in fields
    assert 'from_type_norm' not in fields
    assert fields == ['from_type', 'data_type', 'quality_level', 'del_flag']


# --- client 增强规则 ------------------------------------------------------

def test_payoneer_olive_augment_is_appended(monkeypatch):
    monkeypatch.setattr(quality_filter.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(quality_filter.cqe_config, 'get_model', lambda *a, **k: 'fake-model')

    base = quality_filter.QaQualityFilter(client=None)
    aug = quality_filter.QaQualityFilter(client='payoneer_olive')

    assert aug.system_prompt.startswith(base.system_prompt)
    assert len(aug.system_prompt) > len(base.system_prompt)
    # 平台前缀白名单是最容易被误伤的一条，必须在提示词里
    assert '平台前缀不是个案标识' in aug.system_prompt
    assert '#不通用' in aug.system_prompt


# --- 报告 -----------------------------------------------------------------

def test_report_counts_transitions_and_skips():
    docs = _docs(3)
    decisions = [
        {'_id': 'id1', 'old_level': 'high', 'new_level': 'low', 'tags': ['不通用'],
         'aligned': True, 'skip_reason': ''},
        {'_id': 'id2', 'old_level': 'high', 'new_level': 'high', 'tags': ['优质'],
         'aligned': True, 'skip_reason': ''},
        {'_id': 'id3', 'old_level': 'high', 'new_level': 'high', 'tags': [],
         'aligned': False, 'skip_reason': 'text_mismatch'},
    ]
    report = relabel.build_report(docs, decisions)

    assert report['total'] == 3
    assert report['aligned'] == 2
    assert report['skipped'] == 1
    assert report['changed'] == 1
    assert report['transitions']['high->low'] == 1
    assert report['transitions']['high->high'] == 2
    assert report['skip_reasons'] == {'text_mismatch': 1}
    assert report['samples']['high->low'][0]['q'] == '第1个问题是什么？'
