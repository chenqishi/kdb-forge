from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""answer-source Turn 链路的单群失败隔离。"""
import json
import os
import sys

import pytest


ROOT = str(_PROJECT_ROOT)

from kdb.mining.generation.chatknowledge import gen_knowledge_from_chat as gk


def _chat(send_user, content, ts):
    return {
        'send_user': send_user,
        'send_user_id': send_user,
        'content': content,
        'message_time': ts,
    }


def test_failed_group_does_not_drop_successful_groups_or_advance_watermark(monkeypatch):
    groups = {
        'bad_room': [_chat('同事甲', '坏群答案', '2026-07-30 10:00:00')],
        'good_room': [_chat('同事乙', '好群答案', '2026-07-30 10:01:00')],
    }
    monkeypatch.setattr(gk, 'load_and_reorg_one_robot_data', lambda *args, **kwargs: groups)
    monkeypatch.setattr(gk, 'DirectLLMJsonRequest', lambda *args, **kwargs: object())

    def fake_process(group_name, *args, **kwargs):
        if group_name == 'bad_room':
            raise RuntimeError('simulated group failure')
        return [{'q': '成功问题', 'a': '成功答案', 'source': '同事乙'}]

    monkeypatch.setattr(gk, 'process_one_group_data', fake_process)
    process_record = {}
    run_stats = {}
    config = {
        'robot_1': {
            'all': {
                'type': 'normal',
                'platform': 'mercado',
                'black_group': set(),
            }
        }
    }

    qa_list = gk.process_one_robot_group_data(
        robot_name='robot_1',
        data_file='unused.txt',
        robot_room_type_config=config,
        robot_white_list_dict={},
        robot_room_process_record=process_record,
        need_add_chat_history=False,
        identity_lookup={},
        run_stats=run_stats,
    )

    assert qa_list == [{'q': '成功问题', 'a': '成功答案', 'source': '同事乙'}]
    assert 'bad_room' not in process_record.get('robot_1', {})
    assert process_record['robot_1']['good_room'] == '2026-07-30 10:01:00'
    assert run_stats['groups_succeeded'] == 1
    assert run_stats['groups_failed'] == 1
    assert run_stats['failed_groups'][0]['group_name'] == 'bad_room'


def test_batch_escalates_any_group_failure_and_does_not_save_watermark(monkeypatch, tmp_path):
    data_map_file = tmp_path / 'robot_data_map.txt'
    data_map_file.write_text('robot_1\tmercado\t1\tunused.txt\n', encoding='utf8')
    prompt_map_file = tmp_path / 'prompt_map.txt'
    prompt_map_file.write_text('', encoding='utf8')
    process_record_file = tmp_path / 'process_record.txt'
    white_list_file = tmp_path / 'white_list.txt'
    white_list_file.write_text('', encoding='utf8')
    stats_file = tmp_path / 'llm_stats.json'

    monkeypatch.setattr(gk, 'load_robot_room_type', lambda *args, **kwargs: {})
    monkeypatch.setattr(gk, 'load_white_list_dict', lambda *args, **kwargs: {})
    monkeypatch.setattr(gk, 'load_contact_identity_lookup', lambda *args, **kwargs: {})
    monkeypatch.setattr(gk.common_utils, 'load_map_dict', lambda *args, **kwargs: {})

    def fake_process(*args, **kwargs):
        kwargs['run_stats'].update({
            'robot_name': 'robot_1',
            'groups_seen': 2,
            'groups_eligible': 2,
            'groups_succeeded': 1,
            'groups_failed': 1,
            'failed_groups': [{'group_name': 'bad_room'}],
            'qa_count': 1,
            'llm': {'logical_requests': 2, 'successful_requests': 1, 'failed_requests': 1},
        })
        return [{'q': '成功问题', 'a': '成功答案'}]

    monkeypatch.setattr(gk, 'process_one_robot_group_data', fake_process)
    saved = []
    monkeypatch.setattr(gk, 'save_3file_dict', lambda *args, **kwargs: saved.append(args))

    with pytest.raises(RuntimeError, match='watermarks must fail'):
        gk.run_batch_robot_chat_data(
            str(data_map_file),
            str(tmp_path),
            'unused-room-config.txt',
            str(process_record_file),
            str(white_list_file),
            data_file_field_num=3,
            prompt_file_map=str(prompt_map_file),
            llm_stats_file=str(stats_file),
        )

    assert saved == []
    summary = json.loads(stats_file.read_text(encoding='utf8'))
    assert summary['totals']['groups_failed'] == 1
    assert summary['totals']['logical_requests'] == 2
