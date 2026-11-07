from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""
process_one_data 的类目兜底行为。

背景：群聊自动学习（from_type=chat_auto）链路入库时不传类目，导致文档连
primary_category 字段都不存在，前端按类目筛整批筛不出来（joint_login 实测 1063 条）。
现在新数据没有任何类目来源时兜底到「默认分组」。
"""
import os
import sys

import pytest


from kdb.retrieval.application import search_index_data_interface as sidi
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface


class _FakeEmbedding:
    def text2embedding(self, text):
        return None


@pytest.fixture
def interface(monkeypatch):
    """不走 __init__（会连 ES/embedding 服务），只装配 process_one_data 用到的属性。"""
    obj = SearchDataInterface.__new__(SearchDataInterface)
    obj.embedding_tools = _FakeEmbedding()
    obj.doc_schema_field = {
        'title', 'content', 'data_type', 'platform', 'audit_result', 'quality_level',
        'keywords', 'indexes', 'insert_time', 'update_time', 'from_type', 'ext_info',
        '_id', 'title_embedding', 'content_embedding', 'image_indexes', 'del_flag',
        'from_type_norm', 'category_infos', 'client', 'primary_category', 'dataset',
        'task_id', 'flag', 'multimodal_contents', 'index_name',
    }
    monkeypatch.setattr(sidi, 'gen_keyword_by_title_content', lambda *a, **kw: [])
    return obj


def _chat_auto_doc(**extra):
    data = {
        'title': '重新预约货件后，产品SKU标签需要更换吗？',
        'content': '不需要更换。',
        'data_type': 'qa',
        'from_type': 'chat_auto',
        'platform': 'joint_login',
        'client': 'joint_login',
    }
    data.update(extra)
    return data


def test_new_doc_without_category_falls_back_to_default_group(interface):
    data = _chat_auto_doc()
    assert interface.process_one_data(data, index_name='joint_login') is True

    assert data['primary_category'] == {
        'category_path': '默认分组',
        'category_ids': ['1'],
        'cate1_name': '默认分组',
        'cate1_id': '1',
    }
    assert data['category_infos'] == [{
        'category_id': '1',
        'category_name': '默认分组',
        'score': 1.0,
        'source': 'default',
    }]


def test_existing_category_is_not_overwritten(interface, monkeypatch):
    """有真实类目来源时按 parent chain 构造，不能被默认分组顶掉。"""
    monkeypatch.setattr(
        interface, 'get_category_parent_chain',
        lambda client, cate_id=None, cate_name=None: [
            {'category_id': '2014570264915394561', 'category_name': '运营问题类型'},
            {'category_id': '2014570264915394999', 'category_name': 'Listing管理'},
        ],
    )
    data = _chat_auto_doc(category_infos=[{
        'category_id': '2014570264915394999',
        'category_name': 'Listing管理',
        'score': 1.0,
        'source': 'manual',
    }])
    assert interface.process_one_data(data, index_name='joint_login') is True

    assert data['primary_category']['category_path'] == '运营问题类型-Listing管理'
    assert data['primary_category']['cate1_name'] == '运营问题类型'
    assert data['category_infos'][0]['source'] == 'manual'


def test_name_only_category_is_resolved_from_client_tree(interface, monkeypatch):
    """Payoneer Olive webhook/抽取模型可只传平台名，入库时补 category_id。"""
    monkeypatch.setattr(
        interface, 'get_category_parent_chain',
        lambda client, cate_id=None, cate_name=None: [
            {'category_id': '2084870960369385473', 'category_name': 'Bol'},
        ],
    )
    data = _chat_auto_doc(category_infos=[{
        'category_name': 'Bol', 'score': 1.0, 'source': 'model_platform',
    }])

    assert interface.process_one_data(data, index_name='payoneer_olive') is True
    assert data['category_infos'][0]['category_id'] == '2084870960369385473'
    assert data['primary_category']['category_path'] == 'Bol'


def test_payoneer_olive_falls_back_to_live_category_name_in_tags(interface):
    """model_platform 偶尔回租户名时，仍可用实时类目树匹配问题/标签中的平台名。"""
    chewy_chain = [{'category_id': '2084870960369385474', 'category_name': 'Chewy'}]
    interface.all_client_category_dict = {
        'payoneer_olive': {
            'name_map_dict': {'Chewy': chewy_chain},
            'id_map_dict': {'2084870960369385474': chewy_chain},
        },
    }
    data = _chat_auto_doc(
        platform='payoneer_olive',
        client='payoneer_olive',
        title='Payoneer Chewy 入驻时如何选择产品？',
        tags=['Chewy入驻', '产品链接'],
        ext_info={'model_platform': 'payoneer_olive'},
        category_infos=[{
            'category_name': 'not-in-tree', 'score': 1.0, 'source': 'model_platform',
        }],
    )

    assert interface.process_one_data(data, index_name='payoneer_olive') is True
    assert data['primary_category']['category_path'] == 'Chewy'
    assert data['category_infos'] == [{
        'category_id': '2084870960369385474',
        'category_name': 'Chewy',
        'score': 0.9,
        'source': 'model_tag',
    }]


def test_short_platform_name_requires_word_boundary():
    assert SearchDataInterface._category_name_occurs('Bol 平台如何发货', 'Bol') is True
    assert SearchDataInterface._category_name_occurs('symbol 字段说明', 'Bol') is False


def test_legacy_flag_remains_top_level(interface):
    data = _chat_auto_doc(flag='task-legacy-compat')
    assert interface.process_one_data(data, index_name='joint_login') is True
    assert data['flag'] == 'task-legacy-compat'
    assert 'flag' not in data['ext_info']


def test_update_path_does_not_inject_default_category(interface):
    """带 _id 的更新不能凭空写类目，否则会把已有真实类目覆盖成默认分组。"""
    data = _chat_auto_doc(_id='e930849872a57027283ca4907f4ae90e', title='改个标题',
                          insert_time='2025-03-01 22:24:35')
    assert interface.process_one_data(data, index_name='joint_login') is True

    assert 'primary_category' not in data
    assert 'category_infos' not in data


def test_update_without_insert_time_does_not_crash(interface):
    """回归：有 _id 但没带 insert_time 时曾直接 KeyError 导致整条处理失败。"""
    data = _chat_auto_doc(_id='e930849872a57027283ca4907f4ae90e', title='改个标题')
    assert interface.process_one_data(data, index_name='joint_login') is True

    # 更新不写 insert_time，交给 ES 保留原值；update_time 照常刷新。
    assert 'insert_time' not in data
    assert isinstance(data['update_time'], str)


def test_bad_insert_time_is_corrected(interface):
    data = _chat_auto_doc(insert_time=1740840275)
    assert interface.process_one_data(data, index_name='joint_login') is True
    assert isinstance(data['insert_time'], str)
