# -*- coding: utf-8 -*-
"""insert_data_to_search_index 的 check_duplicate 开关。

背景：无 title 的 segment 判重会被主题级 LLM 误杀（同一篇文档的不同页互判重复），
补插这类数据时需要能显式关掉查重。
"""
import json
import sys
import types
import pytest

sys.path.insert(0, '.')


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """替换掉 SearchDataInterface，只记录 insert_data 收到的参数。"""
    from knowledge_interface_tools import search_index_data_interface as mod

    calls = []

    class FakeInterface(object):
        def __init__(self, *args, **kwargs):
            pass

        def insert_data(self, data, **kwargs):
            calls.append(kwargs)
            data.setdefault('_id', 'fake_id')  # 真实实现会在这里回填 _id
            return (True, '')

    monkeypatch.setattr(mod, 'SearchDataInterface', FakeInterface)

    data_file = tmp_path / 'data.txt'
    data_file.write_text(
        json.dumps({'content': 'x', 'data_type': 'segment', 'platform': 'wayfair'}, ensure_ascii=False) + '\n',
        encoding='utf-8')
    return mod, calls, str(data_file)


def test_default_keeps_config_behaviour(captured):
    mod, calls, data_file = captured
    mod.insert_data_to_search_index(data_file=data_file, config_path='cfg.json', index_name_assign='wayfair')
    assert calls[0]['check_duplicate'] is None, '不传时必须是 None，交给配置文件决定'


def test_false_disables_dedup(captured):
    mod, calls, data_file = captured
    mod.insert_data_to_search_index(data_file=data_file, config_path='cfg.json',
                                    index_name_assign='wayfair', check_duplicate=False)
    assert calls[0]['check_duplicate'] is False


def test_string_false_from_cli_is_coerced(captured):
    """fire 命令行传进来的是字符串。"""
    mod, calls, data_file = captured
    mod.insert_data_to_search_index(data_file=data_file, config_path='cfg.json',
                                    index_name_assign='wayfair', check_duplicate='False')
    assert calls[0]['check_duplicate'] is False


def test_string_true_from_cli_is_coerced(captured):
    mod, calls, data_file = captured
    mod.insert_data_to_search_index(data_file=data_file, config_path='cfg.json',
                                    index_name_assign='wayfair', check_duplicate='True')
    assert calls[0]['check_duplicate'] is True


def test_chat_review_gate_only_attempts_accepted_high(monkeypatch, tmp_path):
    from knowledge_interface_tools import search_index_data_interface as mod

    inserted = []

    class FakeInterface(object):
        def __init__(self, *args, **kwargs):
            pass

        def insert_data(self, data, **kwargs):
            inserted.append(data['title'])
            data.setdefault('_id', 'fake-' + data['title'])
            return (True, '')

    monkeypatch.setattr(mod, 'SearchDataInterface', FakeInterface)
    data_file = tmp_path / 'reviewed.jsonl'
    rows = [
        {'title': 'accept-high', 'content': 'a', 'data_type': 'qa', 'platform': 'payoneer_olive',
         'quality_level': 'high', 'review_decision': 'accept', 'ext_info': {}},
        {'title': 'review-mid', 'content': 'a', 'data_type': 'qa', 'platform': 'payoneer_olive',
         'quality_level': 'mid', 'review_decision': 'review', 'ext_info': {}},
        {'title': 'reject-low', 'content': 'a', 'data_type': 'qa', 'platform': 'payoneer_olive',
         'quality_level': 'low', 'review_decision': 'reject', 'ext_info': {}},
    ]
    data_file.write_text('\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
    result_file = tmp_path / 'insert_result.json'

    stats = mod.insert_data_to_search_index(
        data_file=str(data_file),
        config_path='cfg.json',
        index_name_assign='payoneer_olive',
        allowed_quality_levels='high',
        required_review_decision='accept',
        result_file=str(result_file),
    )

    assert inserted == ['accept-high']
    assert stats['input_num'] == 3
    assert stats['gate_skip_num'] == 2
    assert stats['insert_attempt_num'] == 1
    assert stats['insert_success_num'] == 1
    assert json.loads(result_file.read_text(encoding='utf-8')) == stats
