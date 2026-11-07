# -*- coding: utf-8 -*-
"""生产 Direct LLM 抽取器的通用/客户 Prompt 路由。"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_chat_qa_prompt_routing.py')
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
sys.path.insert(0, ROOT)

from chatknowledge import gen_knowledge_from_chat as gk  # noqa: E402


SCHEDULED_CLIENTS = (
    'joint_login',
    'mars_mind',
    'mercado',
    'mercado_local',
    'payoneer',
    'payoneer_olive',
    'qooten',
    'serene_demo_client',
    'wayfair',
    'wayfair_test',
)


def test_every_scheduled_client_has_extract_and_review_delta():
    for client in SCHEDULED_CLIENTS:
        for stage in ('extract', 'review'):
            path = os.path.join(ROOT, 'chat_qa_extract', 'prompts', f'{stage}.{client}.md')
            assert os.path.isfile(path), path
            assert f'v20260905-{client}' in open(path, encoding='utf-8').read()


def test_direct_llm_uses_base_plus_matching_client_delta_only():
    prompt, meta = gk.resolve_direct_llm_system_prompt(client='joint_login')

    assert 'Chat QA Extract Prompt v20260905-base' in prompt
    assert 'Client Delta v20260905-joint_login' in prompt
    assert 'Client Delta v20260905-payoneer_olive' not in prompt
    assert meta['client'] == 'joint_login'
    assert meta['client_prompt_applied'] is True
    assert len(meta['prompt_hash']) == 12


def test_unknown_or_unsafe_client_falls_back_to_base():
    unknown, unknown_meta = gk.resolve_direct_llm_system_prompt(client='unknown_client')
    unsafe, unsafe_meta = gk.resolve_direct_llm_system_prompt(client='../joint_login')

    assert 'Chat QA Extract Prompt v20260905-base' in unknown
    assert 'Client Delta' not in unknown
    assert unknown_meta['client_prompt_applied'] is False
    assert unsafe == unknown
    assert unsafe_meta['client'] == ''


def test_generated_identity_prompt_is_not_duplicated_into_business_prompt():
    prompt = gk.build_direct_llm_system_prompt(
        system_prompt='自动生成的同事名单和旧业务规则',
        client='payoneer_olive',
    )

    assert '自动生成的同事名单和旧业务规则' not in prompt
    assert 'Client Delta v20260905-payoneer_olive' in prompt


def test_direct_llm_stats_expose_applied_prompt_identity():
    model = gk.DirectLLMJsonRequest(api_key='test-key', client='wayfair')
    stats = model.get_stats()

    assert stats['client'] == 'wayfair'
    assert stats['client_prompt_applied'] is True
    assert len(stats['prompt_hash']) == 12


def test_robot_processor_passes_client_to_direct_llm(monkeypatch):
    captured = {}

    class _FakeModel:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)

        def validate_config(self):
            return None

        def get_stats(self):
            return {}

    monkeypatch.setattr(gk, 'DirectLLMJsonRequest', _FakeModel)
    monkeypatch.setattr(gk, 'load_and_reorg_one_robot_data', lambda *args, **kwargs: {})

    result = gk.process_one_robot_group_data(
        robot_name='robot',
        data_file='unused',
        robot_room_type_config={},
        robot_white_list_dict={},
        identity_lookup={},
        client='mercado_local',
    )

    assert result == []
    assert captured['client'] == 'mercado_local'
