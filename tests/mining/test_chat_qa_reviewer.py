from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
import json
import os
import sys


ROOT = str(_PROJECT_ROOT)

from kdb.mining.quality.chat_qa_extract import reviewer as review_module


def _candidate(**overrides):
    item = {
        'q': 'Bol平台是否支持关闭主店铺后继续运营LVB子账号？',
        'a': '主店铺关闭不会影响LVB子账号。',
        'source': '同事甲',
        'source_identity': '同事/可作为答案来源',
        'source_quote': '主店铺关闭不会影响LVB子账号。',
        'quality_level': 'mid',
        'platform': 'payoneer_olive',
        'client': 'payoneer_olive',
        'model_platform': 'Bol',
        'category_name': 'Bol',
        'category_id': '2084870960369385473',
        'custom_webhook_field': {'trace': 'keep-me'},
        'from_chat_history': '【当前待评估答案】\n同事甲：主店铺关闭不会影响LVB子账号。',
    }
    item.update(overrides)
    return item


def test_ai_source_is_rejected_without_model_call(monkeypatch):
    calls = []
    monkeypatch.setattr(review_module.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(review_module.cqe_config, 'get_model', lambda *a, **k: 'fake-reviewer')
    monkeypatch.setattr(review_module.llm_client, 'request_llm', lambda **kwargs: calls.append(kwargs))
    reviewer = review_module.ChatQAReviewer(client='wayfair')

    result, used_model = reviewer.review(_candidate(source='Wayfair AI助理(运营指导)'))

    assert used_model is False
    assert result['decision'] == 'reject'
    assert 'ai_answer_source' in result['reason_codes']
    assert calls == []


def test_reviewer_preserves_extra_and_category_fields(monkeypatch):
    monkeypatch.setattr(review_module.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(review_module.cqe_config, 'get_model', lambda *a, **k: 'fake-reviewer')
    monkeypatch.setattr(
        review_module.llm_client,
        'request_llm',
        lambda **kwargs: (json.dumps({
            'decision': 'accept',
            'quality_level': 'high',
            'grounded': True,
            'knowledge_scope': 'industry_specific',
            'sensitive': False,
            'temporary': False,
            'valid_until': None,
            'reason_codes': ['stable_platform_rule'],
            'reason': '当前Turn原文完整支撑',
        }, ensure_ascii=False), ''),
    )
    reviewer = review_module.ChatQAReviewer(client='payoneer_olive')
    item = _candidate()

    result, used_model = reviewer.review(item)
    output = review_module.apply_review_result(item, result, reviewer.model)

    assert used_model is True
    assert output['review_decision'] == 'accept'
    assert output['quality_level'] == 'high'
    assert output['q'] == item['q']
    assert output['a'] == item['a']
    assert output['category_name'] == 'Bol'
    assert output['category_id'] == '2084870960369385473'
    assert output['model_platform'] == 'Bol'
    assert output['custom_webhook_field'] == {'trace': 'keep-me'}


def test_mid_or_ungrounded_cannot_auto_import():
    result = review_module.normalize_review_result({
        'decision': 'accept',
        'quality_level': 'mid',
        'grounded': False,
        'knowledge_scope': 'industry_specific',
        'sensitive': False,
        'temporary': False,
    })

    assert result['decision'] == 'review'
    assert result['quality_level'] == 'mid'
    assert {'not_high_quality', 'not_grounded'} <= set(result['reason_codes'])


def test_broken_redaction_is_hard_rejected():
    reasons = review_module.deterministic_reject_reasons(
        _candidate(q='申请[已脱敏]模式需要什么资料？')
    )
    assert 'broken_redaction_placeholder' in reasons


def test_review_batch_keeps_all_buckets_and_stats(monkeypatch, tmp_path):
    qa_file = tmp_path / 'qa.jsonl'
    batch_file = tmp_path / 'batch.txt'
    output_batch = tmp_path / 'review_batch.txt'
    stats_file = tmp_path / 'review_stats.json'
    qa_file.write_text(json.dumps(_candidate(), ensure_ascii=False) + '\n', encoding='utf-8')
    batch_file.write_text(f'robot\tpayoneer_olive\tx\ty\t{qa_file}\n', encoding='utf-8')

    monkeypatch.setattr(review_module.cqe_config, 'load_llm_config', lambda *a, **k: {})
    monkeypatch.setattr(review_module.cqe_config, 'get_model', lambda *a, **k: 'fake-reviewer')
    monkeypatch.setattr(
        review_module.llm_client,
        'request_llm',
        lambda **kwargs: (json.dumps({
            'decision': 'accept', 'quality_level': 'high', 'grounded': True,
            'knowledge_scope': 'industry_specific', 'sensitive': False,
            'temporary': False, 'reason_codes': [], 'reason': 'ok',
        }), ''),
    )

    stats = review_module.review_batch(
        str(batch_file), str(output_batch), client='payoneer_olive', stats_file=str(stats_file)
    )

    reviewed_path = output_batch.read_text(encoding='utf-8').strip().split('\t')[-1]
    buckets = json.loads(open(reviewed_path, encoding='utf-8').read())
    assert len(buckets['high']) == 1
    assert buckets['mid'] == []
    assert buckets['low'] == []
    assert stats['review_accept_num'] == 1
    assert json.loads(stats_file.read_text(encoding='utf-8'))['model_review_request_num'] == 1
