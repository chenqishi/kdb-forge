from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
"""Original HTTP insert -> real business/factory/ES8 with offline ES boundaries."""
import ast
import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import numpy as np
import pytest

from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.retrieval.engines.es_search_interface import EsSearchInterface
from kdb.retrieval.application import search_index_data_interface as business_module
from tests.retrieval.test_es8_interface import FakeClient


@pytest.fixture
def fixture_service(monkeypatch, tmp_path):
    clients = {name: FakeClient(name) for name in ('serverless', 'paas')}
    for client in clients.values():
        client.indices.mapping = {index: {'mappings': {}} for index in ('a', 'b')}
        client.search = Mock(return_value={'_shards': {'failed': 0},
                                          'hits': {'total': {'value': 0}, 'hits': []}})
    monkeypatch.setattr(IndexClientRouter, '_create_client',
                        Mock(side_effect=lambda cfg: clients[cfg['hosts'][0]]))
    embedding = Mock()
    embedding.text2embedding.return_value = np.asarray([1.0, 0.0, 0.0])
    monkeypatch.setattr(business_module, 'EmbeddingTools', Mock(return_value=embedding))
    monkeypatch.setattr(business_module.simility_tools, 'SimilityTools', Mock())
    monkeypatch.setattr(business_module, 'gen_keyword_by_title_content', Mock(return_value=[{'word': 'fixture'}]))
    es_path = tmp_path / 'es.json'
    es_path.write_text(json.dumps({'es_version': '8.17', 'index_name': 'a',
        'vector_fields': {'indexes_embedding': 3}, 'default_provider': 'serverless',
        'providers': {name: {'hosts': [name]} for name in clients},
        'index_routes': {'a': 'serverless', 'b': 'paas'},
        'extra_params': {'ensure_index_on_init': False, 'auto_update_mapping': False}}))
    business_path = tmp_path / 'business.json'
    business_path.write_text(json.dumps({'search_engine_config_path': str(es_path), 'check_duplicate': False}))
    iface = business_module.SearchDataInterface(config_path=str(business_path))
    assert isinstance(iface.engine, EsSearchInterface) and isinstance(iface.engine._impl, EsSearchInterfaceES8)
    path = _PROJECT_ROOT / 'src/kdb/services/retrieval/app.py'
    spec = importlib.util.spec_from_file_location('_insert_extension_actual_service', path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module.SEARCH_DATA_INTERFACE = iface
    return module, iface, clients


async def post_insert(service, payload):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app), base_url='http://offline.invalid') as client:
        return await client.post('/insert', json=copy.deepcopy(payload))


def last_update(clients, provider):
    calls = [params for name, params in clients[provider].calls if name == 'update']
    assert len(calls) == 1
    assert not any(name == 'update' for key, client in clients.items() if key != provider for name, _ in client.calls)
    return calls[0]


@pytest.mark.parametrize('kind', ['qa', 'segment'])
@pytest.mark.parametrize('index,provider', [('a', 'serverless'), ('b', 'paas')])
def test_api_insert_extension_reaches_real_engine(fixture_service, kind, index, provider):
    service, _, clients = fixture_service
    extension = {'from_file_name': 'synthetic.txt', 'nested': {'keep': [1, None]}, 'zero': 0}
    payload = {'_id': 'fixture', 'title': 'question', 'content': 'answer', 'data_type': kind,
               'from_type': 'document', 'index_names': index, 'refresh_imm': True,
               'is_need_llm': False, 'is_update_data': False, 'ext_info': extension,
               'customer_metadata': {'active': False, 'labels': []}}
    before = copy.deepcopy(payload)
    response = asyncio.run(post_insert(service, payload))
    assert response.status_code == 200 and response.json()['success'] is True
    params = last_update(clients, provider)
    assert params['id'] == 'fixture' and params['index'] == index
    doc = params['doc']
    assert doc['ext_info'] == dict(extension, customer_metadata=payload['customer_metadata'])
    assert doc['content'] == 'answer' and doc['data_type'] == kind
    assert len(doc['content_embedding']) == 3
    if kind == 'qa':
        assert doc['title'] == 'question' and len(doc['title_embedding']) == 3
    else:
        assert 'title' not in doc
    assert '_id' not in doc and payload == before


@pytest.mark.parametrize('defined', [None, ['ext_info', 'schema_tag']])
def test_helper_default_schema_and_input_preservation(fixture_service, defined):
    service, _, _ = fixture_service
    request = service.InsertRequest(**{'_id': 'fixture', 'index_names': 'a', 'refresh_imm': True,
        'is_need_llm': False, 'is_update_data': True, 'categoryId': '1', 'categoryName': 'sample',
        'ext_info': {'nested': {'items': [1, None]}, 'collision': 'inner'},
        'collision': 'outer', 'zero': 0, 'false_value': False, 'empty_list': [],
        'empty_object': {}, 'absent': None, 'schema_tag': 'root'})
    before = copy.deepcopy(request.model_dump())
    result = request.get_ext_info_with_extra_fields(defined_fields=defined)
    expected = {'nested': {'items': [1, None]}, 'collision': 'outer', 'zero': 0,
                'false_value': False, 'empty_list': [], 'empty_object': {}}
    if defined is None:
        expected['schema_tag'] = 'root'
    assert result == expected
    assert request.model_dump() == before
    result['nested']['items'].append(2)
    assert request.model_dump() == before


@pytest.mark.parametrize('extension', ['omitted', None, {}, {'new': {'key': 0}}])
def test_partial_update_extension_has_no_control_fields(fixture_service, extension):
    service, _, clients = fixture_service
    payload = {'_id': 'fixture', 'content': 'changed', 'index_names': 'a', 'is_need_llm': False}
    if extension != 'omitted':
        payload['ext_info'] = extension
    response = asyncio.run(post_insert(service, payload))
    assert response.status_code == 200 and response.json()['success'] is True
    params = last_update(clients, 'serverless')
    assert params['id'] == 'fixture' and params['doc_as_upsert'] is True
    assert params['doc']['ext_info'] == (extension if isinstance(extension, dict) else {})
    assert 'title' not in params['doc']
    assert 'id' not in params['doc']['ext_info'] and 'index_names' not in params['doc']['ext_info']


def test_insert_failure_remains_visible(fixture_service):
    service, _, clients = fixture_service
    clients['serverless'].update = Mock(side_effect=RuntimeError('offline ES failure'))
    response = asyncio.run(post_insert(service, {'_id': 'fixture', 'content': 'answer', 'index_names': 'a',
        'ext_info': {'keep': 1}, 'is_need_llm': False}))
    assert response.status_code == 200 and response.json()['success'] is False


def test_request_models_remain_unchanged():
    expected = {'SearchRequest': {'text': ('str', None),
                       'top_k': ('int', '100'),
                       'score_threshold': ('float', '-1'),
                       'index_names': ('str', 'None'),
                       'condition_dicts': ('List[Dict[str, Any]]', 'None'),
                       'search_type': ('str', "'qa'"),
                       'data_type': ('str', "'text'"),
                       'use_synonyms': ('bool', 'False')},
     'WebSearchRequest': {'text': ('str', "''"),
                          'page_size': ('int', '10000'),
                          'page_num': ('int', '1'),
                          'index_names': ('str', 'None'),
                          'client': ('str', 'None'),
                          'need_from_history': ('bool', 'False'),
                          'condition_dicts': ('List[Dict[str, Any]]', '[]'),
                          'score_threshold': ('float', '5.3')},
     'InsertRequest': {'id': ('Optional[str]', "Field(None, alias='_id')"),
                       'title': ('str', 'None'),
                       'content': ('str', 'None'),
                       'multimodal_contents': ('Optional[List[Dict[str, Any]]]', 'None'),
                       'data_type': ('str', 'None'),
                       'from_type': ('str', 'None'),
                       'index_names': ('str', None),
                       'platform': ('str', 'None'),
                       'audit_result': ('int', 'None'),
                       'client': ('str', 'None'),
                       'del_flag': ('int', 'None'),
                       'tags': ('Optional[List[str]]', 'None'),
                       'from_type_norm': ('str', 'None'),
                       'dataset': ('str', 'None'),
                       'task_id': ('str', 'None'),
                       'categoryId': ('str', 'None'),
                       'categoryName': ('str', 'None'),
                       'category_infos': ('Optional[List[Dict[str, Any]]]', 'None'),
                       'ext_info': ('Optional[Dict[str, Any]]', 'None'),
                       'refresh_imm': ('bool', 'False'),
                       'is_need_llm': ('bool', 'False'),
                       'is_update_data': ('bool', 'True'),
                       'Config': {'allow_population_by_field_name': 'True', 'extra': "'allow'"}},
     'DeleteRequest': {'id': ('str', "Field(..., description='数据ID')"),
                       'index_names': ('str', "Field(..., description='索引名称')"),
                       'refresh_imm': ('bool', "Field(False, description='是否立即刷新使删除立即生效')")},
     'ValueCollectionRequest': {'index_name': ('str', "Field(..., description='索引名称')"),
                                'field_name': ('str', "Field(..., description='字段名称')"),
                                'size': ('int', "Field(10000, description='返回值的数量限制')"),
                                'include_doc_count': ('bool', "Field(False, description='是否包含文档数量')"),
                                'extra_query': ('Optional[Dict[str, Any]]',
                                                "Field(None, description='额外的查询条件')")},
     'FromTypeCountRequest': {'index_name': ('Optional[str]',
                                             "Field('', strict=True, description='单个原物理索引名；空名返回0')"),
                              'from_type': ('str',
                                            "Field('chat_auto', strict=True, min_length=1, "
                                            "description='精确来源类型，默认chat_auto')"),
                              'start': ('Optional[datetime]', 'None'),
                              'end': ('Optional[datetime]', 'None')},
     'ListFileNamesRequest': {'index_name': ('str', "Field(..., description='索引名称，必填')"),
                              'keyword': ('Optional[str]', "Field(None, description='文件名关键词筛选，为空则列全部')"),
                              'size': ('int', "Field(200, ge=1, le=1000, description='最多返回多少个文件名')"),
                              'from_type_norm': ('Optional[str]',
                                                 "Field(None, description='来源类型精确筛选；不传、null、空串或仅空白时不限制来源')")},
     'PreviewDeleteByFileRequest': {'index_name': ('str', "Field(..., description='索引名称，必填')"),
                                    'file_names': ('List[str]', "Field(..., description='要删除的来源文件名，可多个')"),
                                    'match_mode': ('str',
                                                   "Field('exact', description='exact(默认)|fuzzy，严格二选一，无兜底')"),
                                    'data_types': ('Optional[List[str]]',
                                                   "Field(None, description='限定 data_type，默认 qa+segment 全删')"),
                                    'audit_results': ('Optional[List[int]]',
                                                      "Field(None, description='限定审核状态，默认不限')"),
                                    'sample_size': ('int', "Field(10, ge=0, le=50, description='返回几条样例供人工确认')")},
     'DeleteByFileRequest': {'index_name': ('str', "Field(..., description='索引名称，必填')"),
                             'file_names': ('List[str]', "Field(..., description='要删除的来源文件名，可多个')"),
                             'match_mode': ('str', "Field('exact', description='exact(默认)|fuzzy，严格二选一，无兜底')"),
                             'data_types': ('Optional[List[str]]',
                                            "Field(None, description='限定 data_type，默认 qa+segment 全删')"),
                             'audit_results': ('Optional[List[int]]', "Field(None, description='限定审核状态，默认不限')")},
     'UpdateByConditionRequest': {'index_name': ('str', "Field(..., description='索引名称')"),
                                  'update_fields': ('Dict[str, Any]',
                                                    "Field(..., description='要更新的字段和值的映射，格式为 {field_name: "
                                                    "new_value}')"),
                                  'conditions': ('List[Dict[str, Any]]',
                                                 "Field(..., description='查询条件列表，每个条件为 {field_name: value} "
                                                 "格式')")},
     'ModifyKnowledgeRequest': {'es_index': ('str', "Field(..., description='ES索引名称')"),
                                'new_query_info': ('Dict[str, Any]',
                                                   "Field(..., description='新查询信息，包含title和content')"),
                                'old_query_info': ('Dict[str, Any]',
                                                   'Field(default={}, '
                                                   "description='旧查询信息，包含title和content；modify_knowledge接口必填，modify_knowledge_direct_update接口可选')"),
                                'search_querys': ('Optional[List[str]]', "Field(None, description='搜索查询列表')"),
                                'write_db_id': ('Optional[str]',
                                                "Field(None, description='写入数据库ID（仅modify_knowledge使用）')"),
                                'allow_insert': ('bool',
                                                 'Field(False, '
                                                 "description='是否允许插入新QA到ES，仅当为True且没有要修改的旧QA时才插入')")}}
    actual = {}
    source = (_PROJECT_ROOT / 'src/kdb/services/retrieval/app.py').read_text(encoding='utf-8')
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name.endswith('Request'):
            actual[node.name] = {}
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    actual[node.name][item.target.id] = (
                        ast.unparse(item.annotation), ast.unparse(item.value) if item.value else None,
                    )
                elif isinstance(item, ast.ClassDef) and item.name == 'Config':
                    actual[node.name]['Config'] = {
                        field.targets[0].id: ast.unparse(field.value)
                        for field in item.body if isinstance(field, ast.Assign)
                    }
    assert len(expected) == 11
    assert actual == expected
