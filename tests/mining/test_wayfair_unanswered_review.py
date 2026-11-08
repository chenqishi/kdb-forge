import kdb.mining.bridges.defaults as _mining_bridges_defaults
import kdb.mining.bridges.retrieval as _mining_bridges_retrieval
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""wayfair_unanswered_review 纯逻辑单测（不打网络、不连库）。

覆盖真正容易出错的部分：坏 JSON 解析、多路检索合并、去重统计、改写降级。
检索/LLM/DB 三条外部依赖走集成验证，不在这里造假数据重复测。
"""

import json
import os
import sys

import pytest

PROJECT_ROOT = str(_PROJECT_ROOT)

import kdb.mining.chat.query_analysis.unanswered_review as wur


# ---------------------------------------------------------------------------
# _extract_json：模型输出的各种坏形态
# ---------------------------------------------------------------------------

def test_extract_json_plain_object():
    assert wur._extract_json('{"verdict": "missing"}') == {'verdict': 'missing'}


def test_extract_json_strips_code_fence():
    text = '```json\n[{"id": 0, "normalized": "Wayfair 回款周期多久"}]\n```'
    assert wur._extract_json(text)[0]['id'] == 0


def test_extract_json_ignores_trailing_prose():
    text = '{"verdict": "covered", "reason": "有"}\n\n以上是我的判断，希望有帮助。'
    assert wur._extract_json(text)['verdict'] == 'covered'


def test_extract_json_repairs_missing_closing_bracket():
    """flash 类模型常见的漏右括号，应能补齐。"""
    text = '[{"id": 0, "normalized": "a"}, {"id": 1, "normalized": "b"}'
    parsed = wur._extract_json(text)
    assert [p['id'] for p in parsed] == [0, 1]


def test_extract_json_not_confused_by_braces_in_strings():
    text = '{"reason": "答案里写了 {占位符} 和 ]"}'
    assert wur._extract_json(text)['reason'] == '答案里写了 {占位符} 和 ]'


def test_extract_json_returns_none_on_garbage():
    assert wur._extract_json('完全不是 JSON') is None
    assert wur._extract_json('') is None


# ---------------------------------------------------------------------------
# query 抽取与去重
# ---------------------------------------------------------------------------

def test_pick_query_text_prefers_regular_then_norm_then_send():
    assert wur.pick_query_text({'regular_content': 'A', 'norm_content': 'B',
                                'send_content': 'C'}) == 'A'
    assert wur.pick_query_text({'regular_content': '', 'norm_content': 'B',
                                'send_content': 'C'}) == 'B'
    assert wur.pick_query_text({'send_content': 'C'}) == 'C'
    assert wur.pick_query_text({'send_content': '  '}) == ''


def test_pick_query_text_collapses_whitespace():
    assert wur.pick_query_text({'send_content': '回款  周期\n多久'}) == '回款 周期 多久'


def test_dedup_queries_counts_and_tracks_time_range():
    rows = [
        {'regular_content': '回款周期', 'create_time': '2026-08-10 10:00:00', 'msg_id': 'm1'},
        {'regular_content': '回款周期', 'create_time': '2026-08-01 09:00:00', 'msg_id': 'm2'},
        {'regular_content': '怎么入驻', 'create_time': '2026-08-05 09:00:00', 'msg_id': 'm3'},
        {'regular_content': '', 'send_content': '', 'create_time': '2026-08-06 09:00:00'},
    ]
    bucket = wur.dedup_queries(rows)
    assert list(bucket.keys()) == ['回款周期', '怎么入驻']
    assert bucket['回款周期']['count'] == 2
    assert bucket['回款周期']['first_seen'] == '2026-08-01 09:00:00'
    assert bucket['回款周期']['last_seen'] == '2026-08-10 10:00:00'
    assert bucket['回款周期']['sample_msg_ids'] == ['m1', 'm2']


def test_dedup_queries_caps_sample_msg_ids_at_three():
    rows = [{'send_content': 'q', 'create_time': '2026-08-01 00:00:00', 'msg_id': f'm{i}'}
            for i in range(6)]
    bucket = wur.dedup_queries(rows)
    assert bucket['q']['count'] == 6
    assert len(bucket['q']['sample_msg_ids']) == 3


# ---------------------------------------------------------------------------
# 检索式构造
# ---------------------------------------------------------------------------

def test_build_search_variants_dedups_and_keeps_order():
    rewrite = {'normalized': '回款周期', 'variants': ['付款周期', '回款周期'],
               'keywords': '回款 周期'}
    assert wur.build_search_variants('回款周期', rewrite) == [
        '回款周期', '付款周期', '回款 周期']


def test_build_search_variants_tolerates_empty_rewrite():
    assert wur.build_search_variants('原问题', {}) == ['原问题']


# ---------------------------------------------------------------------------
# 多路检索合并
# ---------------------------------------------------------------------------

class _FakeSdi:
    """按 query 返回预置文档，模拟多路检索。"""

    def __init__(self, mapping, fail_on=()):
        self.mapping = mapping
        self.fail_on = set(fail_on)
        self.calls = []

    def search_data_by_query(self, query, index_names=None, condition_dicts=None, size=10):
        self.calls.append(query)
        if query in self.fail_on:
            raise RuntimeError('boom')
        return list(self.mapping.get(query, [])), len(self.mapping.get(query, []))


def test_search_knowledge_merges_by_id_keeping_max_score():
    sdi = _FakeSdi({
        'q1': [{'_id': 'a', 'title': 'A', 'content': 'ca', 'similarity': 0.5}],
        'q2': [{'_id': 'a', 'title': 'A', 'content': 'ca', 'similarity': 0.9},
               {'_id': 'b', 'title': 'B', 'content': 'cb', 'similarity': 0.7}],
    })
    docs = _mining_bridges_retrieval.search_knowledge(sdi, ['q1', 'q2'])
    assert [d['_id'] for d in docs] == ['a', 'b']          # 按分数倒排
    assert docs[0]['similarity'] == 0.9                     # 保留最高分
    assert docs[0]['hit_by'] == ['q1', 'q2']                # 记录命中路径


def test_search_knowledge_survives_one_failing_variant():
    """某一路检索抛异常不应让整条 query 作废。"""
    sdi = _FakeSdi({'ok': [{'_id': 'a', 'title': 'A', 'content': '', 'similarity': 0.8}]},
                   fail_on=('bad',))
    docs = _mining_bridges_retrieval.search_knowledge(sdi, ['bad', 'ok'])
    assert [d['_id'] for d in docs] == ['a']


def test_search_knowledge_returns_empty_when_nothing_found():
    assert _mining_bridges_retrieval.search_knowledge(_FakeSdi({}), ['q']) == []


# ---------------------------------------------------------------------------
# 改写：模型漏返 / 坏输出时的降级
# ---------------------------------------------------------------------------

def test_rewrite_queries_falls_back_when_model_omits_ids(monkeypatch):
    """模型只返回部分 id 时，漏的降级为原文检索，不整批作废。"""
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: [
        {'id': 0, 'normalized': '补全后的问题', 'variants': ['变体'], 'keywords': 'k'}])

    out = wur.rewrite_queries(['问题一', '问题二'], batch_size=10)
    assert out['问题一']['normalized'] == '补全后的问题'
    assert out['问题一']['llm_ok'] is True
    assert out['问题二']['normalized'] == '问题二'     # 降级为原文
    assert out['问题二']['llm_ok'] is False


def test_rewrite_queries_falls_back_when_model_returns_nothing(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: None)
    out = wur.rewrite_queries(['问题一'])
    assert out['问题一'] == {'normalized': '问题一', 'variants': [], 'keywords': '',
                             'skip': False, 'skip_reason': '', 'llm_ok': False}


def test_rewrite_queries_caps_variants_at_three(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: [
        {'id': 0, 'normalized': 'n', 'variants': ['a', 'b', 'c', 'd', ''], 'keywords': ''}])
    assert wur.rewrite_queries(['q'])['q']['variants'] == ['a', 'b', 'c']


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------

def test_judge_coverage_returns_missing_without_candidates(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    out = wur.judge_coverage('q', 'q', [])
    assert out['verdict'] == 'missing'
    assert out['llm_ok'] is True


def test_judge_coverage_marks_unknown_when_llm_fails(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: None)
    out = wur.judge_coverage('q', 'q', [{'_id': 'a', 'title': 't', 'content': 'c',
                                         'similarity': 0.5}])
    assert out['verdict'] == 'unknown'
    assert out['llm_ok'] is False


def test_judge_coverage_normalizes_unexpected_verdict(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: {
        'verdict': '不确定', 'reason': 'r', 'evidence_ids': ['a', 'b', 'c', 'd']})
    out = wur.judge_coverage('q', 'q', [{'_id': 'a', 'title': 't', 'content': 'c',
                                         'similarity': 0.5}])
    assert out['verdict'] == 'unknown'
    assert out['evidence_ids'] == ['a', 'b', 'c']   # 最多 3 个


def test_judge_coverage_accepts_valid_verdict(monkeypatch):
    monkeypatch.setattr(wur, '_ensure_llm', lambda: object())
    monkeypatch.setattr(wur, '_request_json', lambda *a, **k: {
        'verdict': 'COVERED', 'reason': '有现成知识', 'evidence_ids': ['a'],
        'suggested_knowledge': ''})
    out = wur.judge_coverage('q', 'q', [{'_id': 'a', 'title': 't', 'content': 'c',
                                         'similarity': 0.9}])
    assert out['verdict'] == 'covered'
    assert out['evidence_ids'] == ['a']


# ---------------------------------------------------------------------------
# 配置与产出
# ---------------------------------------------------------------------------

def test_load_fallback_config_rejects_empty_patterns(tmp_path):
    path = tmp_path / 'cfg.json'
    path.write_text(json.dumps({'fallback_patterns': []}), encoding='utf-8')
    with pytest.raises(ValueError):
        wur.load_fallback_config(str(path))


def test_load_fallback_config_applies_defaults(tmp_path):
    path = tmp_path / 'cfg.json'
    path.write_text(json.dumps({'fallback_patterns': ['无法回答', '  ']}), encoding='utf-8')
    cfg = wur.load_fallback_config(str(path))
    assert cfg['fallback_patterns'] == ['无法回答']
    assert cfg['customers'] == ['wayfair']
    assert cfg['index_names'] == 'wayfair'


def test_shipped_config_matches_the_production_fallback_reply():
    """线上那句兜底话术必须被默认配置命中（回归保护）。"""
    cfg = wur.load_fallback_config()
    reply = ('抱歉，目前我无法回答这个问题，建议您优先咨询账号经理或者是desk团队'
             '（邮箱地址：support@example.invalid）')
    assert any(p in reply for p in cfg['fallback_patterns'])


def test_write_outputs_produces_all_three_files(tmp_path):
    records = [
        {'query': '回款周期', 'count': 3, 'verdict': 'missing', 'normalized': 'n',
         'reason': 'r', 'suggested_knowledge': 's', 'top_score': 0.42,
         'top_title': 't', 'last_seen': '2026-08-10 00:00:00'},
        {'query': '带|竖线的 query', 'count': 1, 'verdict': 'covered', 'normalized': 'n2',
         'reason': 'r2', 'suggested_knowledge': '', 'top_score': 0.98,
         'top_title': 't2', 'last_seen': '2026-08-11 00:00:00'},
    ]
    paths = wur.write_outputs(records, str(tmp_path), '20260820', {'raw_rows': 4})
    for path in paths.values():
        assert os.path.exists(path)
    md = open(paths['markdown'], encoding='utf-8').read()
    assert 'missing' in md and 'covered' in md
    assert '带\\|竖线的 query' in md          # 竖线转义，表格不会被撑破
    lines = open(paths['jsonl'], encoding='utf-8').read().strip().split('\n')
    assert len(lines) == 2 and json.loads(lines[0])['query'] == '回款周期'


# ---------------------------------------------------------------------------
# clean_query_text：群聊 @机器人 的格式噪声
# 真实样本形态取自 2026-08-20 近 30 天的 259 条未答对话（95% 含 @提及）
# ---------------------------------------------------------------------------

def test_clean_strips_quote_tail_and_bot_mentions():
    raw = ('「@Cheryl  WF自动创建了补货计划和入仓订单， 怎么取消」 - - - - - - - '
           '@370631-Mindy-运营  @Wayfair AI助理(运营指导)(🤖)')
    assert wur.clean_query_text(raw) == 'WF自动创建了补货计划和入仓订单， 怎么取消'


def test_clean_strips_dangling_open_quote_after_mention_removal():
    """@ 在收尾引号之前时，剥掉 @ 会连带弄丢 」，前引号不能留下。"""
    raw = '「上架床头柜在US站点失败，需要 CPSC 资质吗？ @Wayfair小汇」 - - - - - - -'
    assert wur.clean_query_text(raw) == '上架床头柜在US站点失败，需要 CPSC 资质吗？'


def test_clean_keeps_plain_question_untouched():
    assert wur.clean_query_text('Wayfair 回款周期是多久') == 'Wayfair 回款周期是多久'


def test_clean_handles_trailing_mention_only():
    assert wur.clean_query_text('C3链接 @🤖') == 'C3链接'


def test_clean_returns_empty_for_mention_only_message():
    """整条只有一个 @机器人，清洗后应为空，不该进入检索。"""
    assert wur.clean_query_text('@🤖') == ''


def test_clean_does_not_eat_hyphens_inside_text():
    """正文里的 CPSC - 16 CFR 1303 不能被尾部分隔线规则误砍。"""
    out = wur.clean_query_text('失败原因提示需要 CPSC - 16 CFR 1303 资质')
    assert 'CPSC - 16 CFR 1303' in out


def test_clean_preserves_inner_quotes_when_unbalanced():
    """引号内还有引号时不脱，避免吃掉正文。"""
    raw = '「他说「这个不行」怎么办'
    assert wur.clean_query_text(raw) == raw


def test_pick_query_text_falls_through_when_cleaning_empties_field():
    """regular_content 清洗后为空时，应回退到 send_content。"""
    row = {'regular_content': '@🤖', 'send_content': '怎么开通CG'}
    assert wur.pick_query_text(row) == '怎么开通CG'


# ---------------------------------------------------------------------------
# reasoning 模型被 max_tokens 截断的告警
# deepseek-v4-pro/flash 的思考 token 计入 max_tokens，预算不足会
# finish_reason='length' + content 为空，只看 content 会误判成模型故障
# ---------------------------------------------------------------------------

def test_warn_when_reasoning_exhausts_max_tokens(caplog):
    import kdb.mining.common.llm.client as llm_client
    result = {
        'choices': [{'finish_reason': 'length', 'message': {'content': ''}}],
        'usage': {'completion_tokens': 30,
                  'completion_tokens_details': {'reasoning_tokens': 30}},
    }
    with caplog.at_level('WARNING'):
        llm_client._warn_if_reasoning_starved(result, '', 'deepseek-v4-pro', 30)
    assert '思考 token' in caplog.text


def test_no_warning_when_content_present(caplog):
    import kdb.mining.common.llm.client as llm_client
    result = {
        'choices': [{'finish_reason': 'length', 'message': {'content': 'x'}}],
        'usage': {'completion_tokens_details': {'reasoning_tokens': 30}},
    }
    with caplog.at_level('WARNING'):
        llm_client._warn_if_reasoning_starved(result, 'x', 'deepseek-v4-pro', 30)
    assert '思考 token' not in caplog.text


def test_no_warning_for_normal_stop_with_empty_content(caplog):
    """finish_reason=stop 的空正文是另一类问题，不该报这条告警。"""
    import kdb.mining.common.llm.client as llm_client
    result = {'choices': [{'finish_reason': 'stop', 'message': {'content': ''}}],
              'usage': {'completion_tokens_details': {'reasoning_tokens': 10}}}
    with caplog.at_level('WARNING'):
        llm_client._warn_if_reasoning_starved(result, '', 'deepseek-v4-pro', 8000)
    assert '思考 token' not in caplog.text


def test_deepseek_models_route_to_official_provider():
    import kdb.mining.common.llm.client as llm_client
    assert llm_client._detect_provider('deepseek-v4-flash') == 'deepseek'
    assert llm_client._detect_provider('deepseek-v4-pro') == 'deepseek'
    assert 'api.deepseek.com' in llm_client._PROVIDER_CONFIGS['deepseek']['api_url']


# ---------------------------------------------------------------------------
# 并发复检：线程池路径与串行路径必须产出一致
# ---------------------------------------------------------------------------

def test_thread_pool_map_preserves_input_order():
    """ThreadPoolExecutor.map 按输入顺序返回，records 与 queries 一一对应。

    复检结果按 query 对齐（报告里 count/verdict 都挂在 query 上），
    顺序错位会导致判定张冠李戴，这里锁死这个契约。
    """
    from concurrent.futures import ThreadPoolExecutor
    import time

    queries = [f'q{i}' for i in range(12)]

    def slow_first(q):
        # 让第一个最慢，若实现按完成顺序收集就会错位
        time.sleep(0.05 if q == 'q0' else 0.001)
        return {'query': q}

    with ThreadPoolExecutor(max_workers=4) as pool:
        out = list(pool.map(slow_first, queries))
    assert [r['query'] for r in out] == queries


def test_search_knowledge_does_not_mutate_caller_conditions():
    """search_data_by_query 会就地补 audit_result；并发下不能改到共享常量。"""
    import copy as _copy
    before = _copy.deepcopy(_mining_bridges_defaults.DEFAULT_CONDITION_DICTS)

    class _MutatingSdi:
        def search_data_by_query(self, query, index_names=None, condition_dicts=None, size=10):
            for cond in condition_dicts:          # 模拟线上就地改条件
                cond['audit_result'] = [1, 2, -1]
                cond['_touched'] = True
            return [], 0

    _mining_bridges_retrieval.search_knowledge(_MutatingSdi(), ['q'])
    assert _mining_bridges_defaults.DEFAULT_CONDITION_DICTS == before


# ---------------------------------------------------------------------------
# 多平台配置：各平台兜底话术完全不同，绝不能共用一份 pattern
# ---------------------------------------------------------------------------

def _multi_cfg(tmp_path):
    p = tmp_path / 'multi.json'
    p.write_text(json.dumps({'platforms': {
        'wayfair': {'customers': ['wayfair'], 'index_names': 'wayfair',
                    'fallback_patterns': ['目前我无法回答这个问题']},
        'mercado_local': {'customers': ['mercado_local'],
                          'index_names': 'mercado_local,mercado_local_admin',
                          'fallback_patterns': ['超出了我目前的知识库覆盖范围']},
    }}, ensure_ascii=False), encoding='utf-8')
    return str(p)


def test_multi_platform_config_selects_requested_platform(tmp_path):
    cfg = wur.load_fallback_config(_multi_cfg(tmp_path), platform='mercado_local')
    assert cfg['customers'] == ['mercado_local']
    assert cfg['fallback_patterns'] == ['超出了我目前的知识库覆盖范围']
    assert cfg['index_names'] == 'mercado_local,mercado_local_admin'


def test_multi_platform_config_requires_platform(tmp_path):
    """多平台配置不给 --platform 必须报错，不能静默取第一个。"""
    with pytest.raises(ValueError) as e:
        wur.load_fallback_config(_multi_cfg(tmp_path))
    assert 'platform' in str(e.value).lower() or '多平台' in str(e.value)


def test_multi_platform_config_rejects_unknown_platform(tmp_path):
    with pytest.raises(ValueError):
        wur.load_fallback_config(_multi_cfg(tmp_path), platform='不存在的平台')


def test_list_platforms(tmp_path):
    assert wur.list_platforms(_multi_cfg(tmp_path)) == ['mercado_local', 'wayfair']


def test_single_platform_config_still_works(tmp_path):
    """旧的单平台格式必须继续可用（向后兼容）。"""
    p = tmp_path / 'single.json'
    p.write_text(json.dumps({'customers': ['wayfair'], 'index_names': 'wayfair',
                             'fallback_patterns': ['无法回答']}, ensure_ascii=False),
                 encoding='utf-8')
    cfg = wur.load_fallback_config(str(p))
    assert cfg['fallback_patterns'] == ['无法回答']


def test_shipped_multi_config_patterns_are_platform_specific():
    """回归：线上各平台话术不同，配置里不能出现张冠李戴。"""
    path = os.path.join(PROJECT_ROOT, 'config', 'unanswered_fallback_patterns.json')
    wf = wur.load_fallback_config(path, platform='wayfair')
    ml = wur.load_fallback_config(path, platform='mercado_local')
    # wayfair 那句实测话术必须只被 wayfair 命中
    reply = ('抱歉，目前我无法回答这个问题，建议您优先咨询账号经理或者是desk团队'
             '（邮箱地址：support@example.invalid）')
    assert any(p in reply for p in wf['fallback_patterns'])
    assert not any(p in reply for p in ml['fallback_patterns'])
    # mercado_local 那句实测话术同理
    ml_reply = '很抱歉，该问题涉及的内容超出了我目前的知识库覆盖范围。已为您记录该问题并提交后台优化'
    assert any(p in ml_reply for p in ml['fallback_patterns'])


# ---------------------------------------------------------------------------
# 尾部分隔线：砍之前要看尾巴里是不是另一个问题
# 实测 259 条里 29 条尾巴含中文，28 条是机器人复述（丢掉无损），
# 1 条是与前半段不同的另一个问题（砍掉就真丢了）
# ---------------------------------------------------------------------------

def test_tail_keeps_distinct_question():
    """尾巴是另一个问题时必须拼回来。"""
    raw = ('「前面是一段很长的机器人回答内容，讲的是促销价格怎么算的事情」 '
           '- - - - - - - @Wayfair AI助理(运营指导)(🤖) 这个开t咨询，选什么路径')
    out = wur.clean_query_text(raw)
    assert '这个开t咨询' in out and '选什么路径' in out


def test_tail_dropped_when_it_merely_restates():
    """尾巴只是把前半段复述一遍时，丢掉无损、不要重复拼接。"""
    raw = ('WF自动创建了补货计划和入仓订单， 怎么取消 - - - - - '
           '@Wayfair AI助理(🤖) WF自动创建了补货计划和入仓订单， 怎么取消')
    out = wur.clean_query_text(raw)
    assert out.count('补货计划') == 1


def test_tail_with_only_bot_name_still_dropped():
    """尾巴只有被 @ 的机器人名（中文字不够）时照常砍掉。"""
    raw = '为何一直打不开财务模块 - - - - - @Wayfair小汇'
    assert wur.clean_query_text(raw) == '为何一直打不开财务模块'
