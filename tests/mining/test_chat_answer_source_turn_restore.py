import kdb.mining.chat._batch_state as _mining_chat__batch_state
import kdb.mining.chat.generation.answer_windows as _chat_generation_answer_windows
import kdb.mining.chat.generation.output as _chat_generation_output
import kdb.mining.chat.identity as _mining_chat_identity
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""历史 answer-source Turn 构建、Prompt 和质量兼容产物的恢复测试。"""
import json
import os
import sys


ROOT = str(_PROJECT_ROOT)

import kdb.mining.chat.generation.batch as gk


def _chat(send_user, content, ts, send_user_id=None):
    return {
        'send_user': send_user,
        'send_user_id': send_user_id or send_user,
        'content': content,
        'message_time': ts,
    }


def test_explicit_answer_source_overrides_contact_default():
    role, reason = _mining_chat_identity.infer_speaker_identity(
        '同事甲',
        answer_source_names={'同事甲'},
        contact_identity={
            'role': _mining_chat__batch_state.QUESTION_SOURCE_ROLE,
            'reason': '通讯录默认外部联系人',
        },
    )

    assert role == _mining_chat__batch_state.COLLEAGUE_SOURCE_ROLE
    assert reason == '命中平台同事名单'


def test_explicit_silent_contact_vetoes_stale_answer_source_name():
    role, reason = _mining_chat_identity.infer_speaker_identity(
        'Wayfair AI助理(运营指导)',
        answer_source_names={'Wayfair AI助理(运营指导)'},
        contact_identity={
            'role': _mining_chat_identity.UNKNOWN_SOURCE_ROLE,
            'reason': '企业微信通讯录标记为静默',
        },
    )

    assert role == _mining_chat_identity.UNKNOWN_SOURCE_ROLE
    assert reason == '企业微信通讯录标记为静默'


def test_ai_keyword_vetoes_contact_and_stale_answer_source_name():
    role, reason = _mining_chat_identity.infer_speaker_identity(
        'Wayfair AI助理(运营指导)',
        answer_source_names={'Wayfair AI助理(运营指导)'},
        contact_identity={
            'role': _mining_chat__batch_state.COLLEAGUE_SOURCE_ROLE,
            'reason': '企业微信通讯录标记为同事',
        },
    )

    assert role == _mining_chat_identity.UNKNOWN_SOURCE_ROLE
    assert reason == '发言人名称包含AI标识'


def test_ai_keyword_filter_does_not_match_letters_inside_human_name():
    assert _mining_chat_identity.has_ai_speaker_keyword('Wayfair AI助理') is True
    assert _mining_chat_identity.has_ai_speaker_keyword('wayfair-ai-bot') is True
    assert _mining_chat_identity.has_ai_speaker_keyword('Aimee Hu') is False
    assert _mining_chat_identity.has_ai_speaker_keyword('Daisy') is False


def test_answer_source_prompt_names_drop_ai_keyword_accounts():
    prompt = '# 你的同事如下\n"""\nWayfair AI助理(运营指导)\nWei Wang\n"""'

    assert _mining_chat_identity.extract_answer_source_names(prompt) == {'Wei Wang'}


def test_ai_keyword_message_cannot_build_answer_turn():
    messages = [
        _chat('客户甲', '怎么看资金回款？', '2026-09-04 12:22:18', 'customer-1'),
        _chat('Wayfair AI助理(运营指导)', '在财务页面查看。', '2026-09-04 12:22:30', 'ai-1'),
        _chat('Wei Wang', '在付款摘要中查看。', '2026-09-04 12:23:00', 'staff-1'),
    ]

    turns = _chat_generation_answer_windows.build_answer_source_turns(
        messages,
        answer_source_names={'Wayfair AI助理(运营指导)', 'Wei Wang'},
        platform='wayfair_test',
    )

    assert len(turns) == 1
    assert turns[0]['target_messages'][0]['send_user'] == 'Wei Wang'


def test_answer_turn_uses_context_only_for_question_and_merges_same_sender():
    messages = [
        _chat('客户甲', '审核怎么催？', '2026-07-27 13:40:57', 'customer-1'),
        _chat('同事甲', '没有催审通道，等系统按顺序处理', '2026-07-27 13:42:44', 'staff-1'),
        _chat('同事甲', 'under review 是核价和选品环节', '2026-07-27 13:43:11', 'staff-1'),
        _chat('客户甲', '谢谢', '2026-07-27 13:43:20', 'customer-1'),
    ]

    turns = _chat_generation_answer_windows.build_answer_source_turns(
        messages,
        answer_source_names={'同事甲'},
        platform='mercado',
    )

    assert len(turns) == 1
    assert len(turns[0]['target_messages']) == 2

    prompt = _chat_generation_answer_windows.build_answer_window_prompt(
        'room-1',
        messages,
        turns[0],
        answer_source_names={'同事甲'},
        platform='mercado',
    )
    assert 'customer_or_platform: 美客多' in prompt
    assert '客户甲/问题来源：审核怎么催？' in prompt
    assert '同事甲/当前待评估答案：没有催审通道' in prompt
    assert '同事甲/当前待评估答案：under review 是核价和选品环节' in prompt
    assert '客户甲/当前待评估答案' not in prompt


def test_customer_message_closes_answer_turn():
    messages = [
        _chat('同事甲', '第一段答案', '2026-07-27 10:00:00', 'staff-1'),
        _chat('客户甲', '追问', '2026-07-27 10:00:10', 'customer-1'),
        _chat('同事甲', '第二段答案', '2026-07-27 10:00:20', 'staff-1'),
    ]

    turns = _chat_generation_answer_windows.build_answer_source_turns(
        messages,
        answer_source_names={'同事甲'},
        platform='mercado',
    )
    assert [len(turn['target_messages']) for turn in turns] == [1, 1]


def test_direct_quality_bucket_keeps_downstream_contract(tmp_path):
    qa_file = tmp_path / 'qa.jsonl'
    batch_file = tmp_path / 'batch.txt'
    output_batch = tmp_path / 'quality_batch.txt'
    qa_file.write_text(
        '\n'.join([
            json.dumps({'q': 'q1', 'a': 'a1', 'quality_level': 'high'}, ensure_ascii=False),
            json.dumps({'q': 'q2', 'a': 'a2', 'quality_level': 'mid'}, ensure_ascii=False),
        ]) + '\n',
        encoding='utf-8',
    )
    batch_file.write_text('robot\tmercado\tx\ty\t%s\n' % qa_file, encoding='utf-8')

    _chat_generation_output.build_direct_llm_quality_batch(str(batch_file), str(output_batch))

    fields = output_batch.read_text(encoding='utf-8').strip().split('\t')
    quality_file = fields[-1]
    data = json.loads(open(quality_file, encoding='utf-8').read())
    assert len(data['high']) == 1
    assert len(data['mid']) == 1
    assert data['low'] == []
    assert quality_file.endswith('_direct_llm_quality_and_resplit.txt')
