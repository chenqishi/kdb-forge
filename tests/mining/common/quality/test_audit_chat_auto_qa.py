from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""
自动学习 QA 二次审核的行为测试（全部用假 LLM / 假 ES，不打真实接口）。

重点是这几条不能错的语义：
  1. 圈定条件必须按 `from_type`，不能按 `from_type_norm`（线上 norm 里根本没有 chat_auto）
  2. 判不出来（模型返回空 / JSON 解不出 / verdict 不合法）→ **保持原档位**，绝不默认降级
  3. 答案来自客户 / 与业务无关 / 不通用 → low
  4. 群昵称带后缀（`Stacy Yao@橄榄枝计划 出差中回复慢`）也要能匹配上同事名单
  5. 只对档位真正变化的文档发写请求；dry-kdb.entrypoints.cli.generate_segments 不产生任何写请求
"""
import json
import os
import sys

import pytest

ROOT = str(_PROJECT_ROOT)

from kdb.shared.clients.app_role_config import extract_colleague_names
import kdb.mining.common.quality.audit_generated_qa as audit

CHAT = '''在群[45403736923@chatroom]中，有以下聊天记录：
Rodman LUO(橄榄枝计划小助手 Rodman Luo) : 以下是Bol电商平台的入驻要求，请问您符合吗？
赵samsam: 我这边有德国公司主体，然后目前刚开始做Kaufland平台。
Rodman LUO(橄榄枝计划小助手 Rodman Luo) : 那您公司其他主体之前在欧洲的体量怎样呢？
赵samsam: 额 过去一年我们所有店铺GMV大概是100W欧元左右。然后单店铺销售额最高大概是11W欧元左右。
'''
PEERS = ['Rodman LUO', 'Stacy Yao', 'Amy Wang']


def test_target_query_filters_by_from_type_not_norm():
    q = audit.build_target_query()
    terms = [list(f.values())[0] for f in q['bool']['filter']]
    fields = {k for t in terms for k in t}
    assert 'from_type' in fields
    assert 'from_type_norm' not in fields
    assert {'term': {'from_type': 'chat_auto'}} in q['bool']['filter']
    assert {'terms': {'audit_result': [-1]}} in q['bool']['filter']


def test_target_query_random_sample_wraps_function_score():
    q = audit.build_target_query(random_seed=42)
    assert q['function_score']['random_score']['seed'] == 42
    assert 'bool' in q['function_score']['query']


def test_annotate_finds_customer_as_answer_speaker():
    """用户点名的那条：答案是卖家自报的 GMV，说话人不在同事名单里"""
    ann = audit.annotate_chat_history(
        CHAT, '额 过去一年我们所有店铺GMV大概是100W欧元左右。然后单店铺销售额最高大概是11W欧元左右。',
        PEERS)
    assert ann['answer_speaker'] == '赵samsam'
    assert ann['answer_speaker_is_colleague'] is False
    assert 'Rodman LUO(橄榄枝计划小助手 Rodman Luo)' in ann['colleagues_in_chat']


def test_annotate_matches_nickname_with_suffix():
    """群昵称普遍带 @部门/状态后缀，精确相等匹配不上，必须用归一化子串"""
    chat = 'Stacy Yao@橄榄枝计划 出差中回复慢: 需要两年以上营业执照\n卖家小李: 好的\n'
    ann = audit.annotate_chat_history(chat, '需要两年以上营业执照', PEERS)
    assert ann['answer_speaker_is_colleague'] is True
    assert ann['colleagues_in_chat'] == ['Stacy Yao@橄榄枝计划 出差中回复慢']


def test_annotate_answer_speaker_unknown_when_no_match():
    ann = audit.annotate_chat_history(CHAT, '完全对不上的一段答案文本', PEERS)
    assert ann['answer_speaker'] == ''
    assert ann['answer_speaker_is_colleague'] is None


@pytest.mark.parametrize('result', [
    {},                                             # 模型返回空 / 解析失败
    {'verdict': 'maybe'},                           # 非法 verdict
    {'business_related': True, 'generic': True},    # 缺 verdict
])
def test_undecidable_keeps_old_level(result):
    level, skip = audit.decide_level('high', result)
    assert level == 'high'
    assert skip


@pytest.mark.parametrize('result,expected', [
    ({'verdict': 'keep', 'answer_source': 'colleague',
      'business_related': True, 'generic': True, 'tags': []}, 'high'),
    ({'verdict': 'downgrade', 'answer_source': 'customer',
      'business_related': True, 'generic': True, 'tags': ['答案来自客户']}, 'low'),
    ({'verdict': 'downgrade', 'answer_source': 'colleague',
      'business_related': False, 'generic': True, 'tags': ['不相关']}, 'low'),
    ({'verdict': 'downgrade', 'answer_source': 'colleague',
      'business_related': True, 'generic': False, 'tags': ['不通用']}, 'low'),
    ({'verdict': 'downgrade', 'answer_source': 'colleague',
      'business_related': True, 'generic': True, 'tags': ['不清晰']}, 'mid'),
    ({'verdict': 'downgrade', 'answer_source': 'colleague',
      'business_related': True, 'generic': True, 'tags': []}, 'mid'),
])
def test_decide_level(result, expected):
    level, skip = audit.decide_level('high', result)
    assert (level, skip) == (expected, '')


def test_parse_llm_json_handles_code_fence_and_prose():
    text = '好的，判定结果如下：\n```json\n{"verdict": "keep", "tags": []}\n```\n'
    assert audit._parse_llm_json(text) == {'verdict': 'keep', 'tags': []}
    assert audit._parse_llm_json('not a json at all') is None
    assert audit._parse_llm_json('') is None


def test_prompt_carries_context_and_speaker_hint():
    doc = {'title': 'Bol-GMV是多少', 'content': '大概100W欧元', 'chat_history': CHAT}
    ann = audit.annotate_chat_history(CHAT, '大概100W欧元', PEERS)
    prompt = audit.build_judge_prompt(doc, ann)
    assert 'Bol-GMV是多少' in prompt
    assert '赵samsam' in prompt          # 聊天记录原文进了 prompt
    assert 'answer_source' in prompt
    assert 'official' in prompt          # 平台官方经理这条豁免必须在


def test_prompt_truncates_history_from_the_tail():
    """答案在对话结尾，截断必须保尾"""
    doc = {'title': 'q', 'content': 'a', 'chat_history': 'x' * 500 + '结尾的关键内容'}
    prompt = audit.build_judge_prompt(doc, {'colleagues_in_chat': []}, max_history_chars=100)
    assert '结尾的关键内容' in prompt
    assert '前文已截断' in prompt


class _FakeEs:
    """只实现 _bulk 需要的 _request；bulk_update_doc 是脚本里的模块级函数，
    不能依赖 EsHttpClient 上的同名方法（生产机器上还没有它）"""

    def __init__(self):
        self.calls = []

    def _request(self, method, path, body=None, raw_body=None):
        assert (method, path) == ('POST', '/_bulk')
        lines = [json.loads(x) for x in raw_body.strip().split('\n')]
        updates = [(lines[i]['update']['_id'], lines[i + 1]['doc'])
                   for i in range(0, len(lines), 2)]
        self.calls.append((lines[0]['update']['_index'], updates))
        return 200, {'items': [{'update': {'_id': u[0]}} for u in updates]}


def test_apply_updates_only_writes_changed(tmp_path):
    decisions = [
        {'_id': 'a', 'old_level': 'high', 'new_level': 'low', 'changed': True, 'skip_reason': ''},
        {'_id': 'b', 'old_level': 'high', 'new_level': 'high', 'changed': False, 'skip_reason': ''},
        # 判不出来的即使 changed 被误置也不能写
        {'_id': 'c', 'old_level': 'high', 'new_level': 'high', 'changed': True,
         'skip_reason': 'empty_llm_result'},
    ]
    es = _FakeEs()
    rollback = str(tmp_path / 'rollback.jsonl')
    res = audit.apply_updates(es, 'idx', decisions, rollback)
    assert res['updated'] == 1
    assert es.calls[0][1] == [('a', {'quality_level': 'low'})]
    rows = [json.loads(x) for x in open(rollback, encoding='utf-8')]
    assert rows == [{'_id': 'a', 'quality_level': 'high'}]


def test_rollback_restores_old_level(tmp_path):
    path = tmp_path / 'rollback.jsonl'
    path.write_text('{"_id": "a", "quality_level": "high"}\n', encoding='utf-8')
    es = _FakeEs()
    audit.run_rollback(es, 'idx', str(path))
    assert es.calls[0][1] == [('a', {'quality_level': 'high'})]


def test_extract_colleague_names_handles_all_value_shapes():
    items = [
        {'configKey': 'peer', 'configValue': [{'userName': 'Amy Wang'},
                                              {'userName': 'Amy Wang'},   # 重复要去掉
                                              {'nickname': '没有 userName'}]},
        {'configKey': 'teacher', 'configValue': {'userName': 'Mo Li'}},
        {'configKey': 'management', 'configValue': '  Tony Liu  '},
        {'configKey': 'blacklist', 'configValue': [{'userName': '不该出现'}]},
    ]
    assert extract_colleague_names(items) == ['Amy Wang', 'Mo Li', 'Tony Liu']


def test_substantive_false_downgrades_to_low():
    """业务侧 91.7% 的拒绝理由是「无实质答案」，这一维度不能只藏在 verdict 里"""
    level, skip = audit.decide_level('high', {
        'verdict': 'downgrade', 'answer_source': 'colleague',
        'business_related': True, 'generic': True, 'substantive': False, 'tags': []})
    assert (level, skip) == ('low', '')


def test_prompt_asks_for_substantive_field():
    prompt = audit.build_judge_prompt(
        {'title': 'q', 'content': 'a', 'chat_history': 'x: y\n'}, {'colleagues_in_chat': []})
    assert 'substantive' in prompt
    assert '空确认' in prompt
