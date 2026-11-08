from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
import os
import sys
import types


ROOT = str(_PROJECT_ROOT)

from kdb.mining.common.schema.qa_records import trans_qa_to_search_data


def test_payoneer_olive_model_platform_becomes_category_name():
    data = trans_qa_to_search_data({
        'q': 'Bol平台如何处理订单？',
        'a': '按后台步骤处理。',
        'platform': 'payoneer_olive',
        'client': 'payoneer_olive',
        'model_platform': 'Bol',
        'marketplace': 'Bol',
        'quality_level': 'high',
        'review_decision': 'accept',
    })

    assert data['platform'] == 'payoneer_olive'
    assert data['client'] == 'payoneer_olive'
    assert data['category_infos'] == [{
        'category_name': 'Bol', 'score': 1.0, 'source': 'model_platform'
    }]
    assert data['ext_info']['model_platform'] == 'Bol'
    assert data['review_decision'] == 'accept'


def test_explicit_category_input_takes_priority_over_inferred_platform():
    data = trans_qa_to_search_data(
        {
            'q': 'q', 'a': 'a', 'platform': 'payoneer_olive',
            'model_platform': 'Chewy', 'quality_level': 'high',
        },
        category_id='2084870960369385473',
        category_name='Bol',
    )

    assert data['category_infos'] == [{
        'category_id': '2084870960369385473',
        'category_name': 'Bol',
        'score': 1.0,
        'source': 'manual',
    }]


def test_category_infos_accepts_camel_case_webhook_fields():
    data = trans_qa_to_search_data({
        'q': 'Chewy 如何入驻？',
        'a': '按平台招商流程提交。',
        'platform': 'payoneer_olive',
        'category_infos': [{
            'categoryId': 2084862924493963265,
            'categoryName': 'Chewy',
            'score': 0.95,
            'source': 'webhook',
        }],
    })

    assert data['category_infos'] == [{
        'category_id': 2084862924493963265,
        'category_name': 'Chewy',
        'score': 0.95,
        'source': 'webhook',
    }]


def test_legacy_chat_qa_ext_fields_are_preserved_without_unknown_passthrough():
    legacy_values = {
        'quality_reason': '旧抽取质量原因',
        'knowledge_type': '平台规则',
        'business_tags': ['履约'],
        'scenario_tags': ['发货'],
        'entity_tags': ['订单'],
        'es_tags': ['Bol'],
        'reuse_scope': '跨客户可复用',
        'should_enter_reuse_evaluation': True,
        'confidence': 0.98,
        'source_quote': '答案原话',
        'candidate_answer_time': '2026-06-25 18:03:26',
        'from_user': '同事甲',
        'source': '同事甲',
        'client': 'payoneer_olive',
        'marketplace': 'Bol',
        'model_platform': 'Bol',
        'supplement': {'images': [{'address': '/legacy/image.png'}]},
        'supplement_mapping_error': ['missing-public-url'],
    }
    data = trans_qa_to_search_data({
        'q': 'Bol 如何发货？',
        'a': '按平台面单发货。',
        'platform': 'payoneer_olive',
        **legacy_values,
        'info': {'do_not_write': True},
        'reference_knowledge': '不要新增该字段',
        'evidence': '不要新增该字段',
        'ext_info': {
            'from_chat_history': '历史上下文',
            'unknown_nested_field': '不要透传',
        },
    }, task_id='task-legacy-compat')

    for field_name, value in legacy_values.items():
        assert data['ext_info'][field_name] == value
    assert data['ext_info']['from_chat_history'] == '历史上下文'
    assert data['task_id'] == 'task-legacy-compat'
    assert data['flag'] == 'task-legacy-compat'
    for forbidden in ('info', 'reference_knowledge', 'evidence', 'unknown_nested_field'):
        assert forbidden not in data
        assert forbidden not in data['ext_info']


def test_known_legacy_field_can_be_restored_from_upstream_ext_info():
    data = trans_qa_to_search_data({
        'q': 'q', 'a': 'a', 'platform': 'mercado',
        'ext_info': {
            'source': '旧同事',
            'candidate_answer_time': '2026-06-12 10:28:39',
            'quality_reason': '旧原因',
            'is_qualified': True,
            'tags': ['历史标签'],
        },
    })

    assert data['ext_info']['source'] == '旧同事'
    assert data['ext_info']['candidate_answer_time'] == '2026-06-12 10:28:39'
    assert data['ext_info']['quality_reason'] == '旧原因'
    assert data['ext_info']['is_qualified'] is True
    assert data['tags'] == ['历史标签']
