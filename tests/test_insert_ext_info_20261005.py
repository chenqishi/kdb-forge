"""Original HTTP insert -> real business/factory/ES8 with offline ES boundaries."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_insert_ext_info_20261005.py')
import ast
import asyncio
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import httpx
import numpy as np
import pytest

from knowledge_interface_tools.es8_client_router import IndexClientRouter
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
from knowledge_interface_tools.es_search_interface import EsSearchInterface
from knowledge_interface_tools import search_index_data_interface as business_module
from test_es8_interface import FakeClient


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
    path = Path(__legacy_source_file__).resolve().parents[1] / 'knowledge_database_search_service/src/knowledge_database_search_es.py'
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
    root = Path(__legacy_source_file__).resolve().parents[1]
    path = 'knowledge_database_search_service/src/knowledge_database_search_es.py'
    baseline = subprocess.run(['git', 'show', 'f873a5930bb42630374f6045b6e2de834a9319f4:' + path],
                              cwd=root, check=True, capture_output=True, text=True).stdout
    snapshots = []
    for text in (baseline, (root / path).read_text()):
        snapshots.append({node.name: [ast.dump(item, include_attributes=False) for item in node.body
            if isinstance(item, ast.AnnAssign) or isinstance(item, ast.ClassDef) and item.name == 'Config']
            for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name.endswith('Request')})
    assert len(snapshots[0]) == 10
    assert snapshots[0] == {name: snapshots[1][name] for name in snapshots[0]}
    assert set(snapshots[1]) - set(snapshots[0]) == {"FromTypeCountRequest"}
