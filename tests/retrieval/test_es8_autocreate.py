import kdb.retrieval.application.runtime as retrieval_runtime
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
"""Real old HTTP/business/factory/ES8 methods with external ES/embedding doubles."""
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
from elasticsearch import ApiError
from elasticsearch import BadRequestError
from elasticsearch import NotFoundError
from elastic_transport import ApiResponseMeta
from elastic_transport import HttpHeaders
from elastic_transport import NodeConfig

import kdb.retrieval.application.search_index_data_interface as business
from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.retrieval.engines.factory import EsSearchInterface
from tests.retrieval.test_es8_interface import FakeClient


class FixtureClient(FakeClient):
    def __init__(self, provider):
        super().__init__(provider)
        self.maps = {}
        self.docs = {}
        self.create_requests = []
        self.races = set()
        self.denied = set()
        self.failed_queries = set()
        self.indices.exists = Mock(side_effect=self.exists)
        self.indices.create = Mock(side_effect=self.create)
        self.indices.get_mapping = Mock(side_effect=self.get_mapping)
        self.indices.put_mapping = Mock(return_value={'acknowledged': True})

    def exists(self, index):
        return index in self.maps

    def create(self, index, settings, mappings):
        self.create_requests.append({'index': index, 'settings': copy.deepcopy(settings),
                                     'mappings': copy.deepcopy(mappings)})
        meta = ApiResponseMeta(403, '1.1', HttpHeaders({}), 0, NodeConfig('http', 'fake', 9200))
        if index in self.denied:
            raise ApiError('create denied', meta, {'error': {'type': 'security_exception'}})
        self.maps[index] = copy.deepcopy(mappings)
        self.docs.setdefault(index, [])
        if index in self.races:
            meta = ApiResponseMeta(400, '1.1', HttpHeaders({}), 0, NodeConfig('http', 'fake', 9200))
            raise BadRequestError('another worker created it', meta,
                                  {'error': {'type': 'resource_already_exists_exception'}})
        return {'acknowledged': True}

    def get_mapping(self, index):
        return {index: {'mappings': copy.deepcopy(self.maps[index])}}

    def search(self, **kwargs):
        self.calls.append(('search', copy.deepcopy(kwargs)))
        index = kwargs['index']
        if index not in self.maps or index in self.failed_queries:
            meta = ApiResponseMeta(404, '1.1', HttpHeaders({}), 0, NodeConfig('http', 'fake', 9200))
            raise NotFoundError('missing index', meta,
                                {'error': {'type': 'index_not_found_exception', 'reason': index}})
        docs = self.docs.get(index, [])
        return {'_shards': {'total': 1, 'successful': 1, 'failed': 0},
                'hits': {'total': {'value': len(docs), 'relation': 'eq'},
                         'hits': [{'_index': index, '_id': doc['_id'], '_score': 1.0,
                                   '_source': {k: copy.deepcopy(v) for k, v in doc.items() if k != '_id'}}
                                  for doc in docs[:kwargs['size']]]}}


@pytest.fixture
def fixture_service(monkeypatch, tmp_path):
    clients = {name: FixtureClient(name) for name in ('serverless', 'paas')}
    monkeypatch.setattr(IndexClientRouter, '_create_client',
                        Mock(side_effect=lambda cfg: clients[cfg['hosts'][0]]))
    config = {'es_version': '8.17', 'index_name': 'public_s',
              'vector_fields': {'indexes_embedding': 3}, 'default_provider': 'serverless',
              'providers': {name: {'hosts': [name]} for name in clients},
              'index_routes': {'*_s': 'serverless', '*_p': 'paas'},
              'extra_params': {'ensure_index_on_init': True, 'auto_update_mapping': False}}
    mapping = EsSearchInterfaceES8(config=dict(config, extra_params={'ensure_index_on_init': False}))._build_mapping()
    for suffix, provider in [('s', 'serverless'), ('p', 'paas')]:
        index = 'public_' + suffix
        clients[provider].maps[index] = copy.deepcopy(mapping)
        clients[provider].docs[index] = [{'_id': 'public-hit', 'title': 'synthetic question',
            'content': 'synthetic answer', 'data_type': 'qa', 'del_flag': 0, 'audit_result': 2,
            'title_embedding': [1.0, 0.0, 0.0], 'content_embedding': [1.0, 0.0, 0.0],
            'indexes': [{'text': 'synthetic question', 'embedding': [1.0, 0.0, 0.0]}],
            'ext_info': {'from_file_name': 'synthetic.txt'}}]
    embedding = Mock()
    embedding.text2embedding.return_value = np.asarray([1.0, 0.0, 0.0])
    monkeypatch.setattr(business, 'EmbeddingTools', Mock(return_value=embedding))
    monkeypatch.setattr(business.simility_tools, 'SimilityTools', Mock())
    es_path = tmp_path / 'es.json'
    es_path.write_text(json.dumps(config))
    business_path = tmp_path / 'business.json'
    business_path.write_text(json.dumps({'search_engine_config_path': str(es_path), 'check_duplicate': False}))
    iface = business.SearchDataInterface(config_path=str(business_path))
    assert isinstance(iface.engine, EsSearchInterface)
    assert isinstance(iface.engine._impl, EsSearchInterfaceES8)
    path = _PROJECT_ROOT / 'src/kdb/entrypoints/http/retrieval/app.py'
    spec = importlib.util.spec_from_file_location('_autocreate_actual_old_service', path)
    service = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, service)
    spec.loader.exec_module(service)
    retrieval_runtime.SEARCH_DATA_INTERFACE = iface
    return service, iface.engine._impl, clients


async def post_query(service, endpoint, request):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app),
                                 base_url='http://offline.invalid') as client:
        return await client.post(endpoint, json=copy.deepcopy(request))


@pytest.mark.parametrize('suffix,provider', [('s', 'serverless'), ('p', 'paas')])
@pytest.mark.parametrize('kind', ['qa', 'segment'])
@pytest.mark.parametrize('private_first', [True, False])
@pytest.mark.parametrize('endpoint', ['/search', '/web_search'])
def test_joint_http_autocreates_empty_private_and_retains_public(fixture_service, suffix, provider, kind, private_first, endpoint):
    service, engine, clients = fixture_service
    public, private = 'public_' + suffix, 'private_' + suffix
    clients[provider].docs[public][0]['data_type'] = kind
    names = [private, public] if private_first else [public, private]
    request = {'text': 'synthetic question', 'index_names': ','.join(names),
               'condition_dicts': [{'data_type': kind}], 'search_type': kind,
               'top_k': 3, 'page_size': 3, 'use_synonyms': True}
    response = asyncio.run(post_query(service, endpoint, request))
    assert response.status_code == 200
    wire = response.json()
    hits = wire['results']
    id_field = 'id' if endpoint == '/search' else '_id'
    assert len(hits) == 1 and hits[0][id_field] == 'public-hit', wire
    assert hits[0].get('q') != '检索结果错误'
    assert hits[0]['ext_info'] == {'from_file_name': 'synthetic.txt'}
    assert hits[0]['score'] > 0
    assert clients[provider].docs[private] == []
    creates = clients[provider].create_requests
    assert [item['index'] for item in creates] == [private]
    props = creates[0]['mappings']['properties']
    assert props['indexes']['type'] == 'nested'
    assert props['indexes']['properties']['embedding']['index_options']['type'] == 'hnsw'
    assert props['title_embedding']['dims'] == 3
    assert not clients[provider].indices.put_mapping.called
    assert engine.search_multi({}, index_names=private) == ([], 0)
    assert len(clients[provider].create_requests) == 1


@pytest.mark.parametrize('suffix,provider', [('s', 'serverless'), ('p', 'paas')])
@pytest.mark.parametrize('private_first', [True, False])
def test_disabled_ensure_still_keeps_public_on_missing_index(fixture_service, suffix, provider, private_first, caplog):
    _, engine, clients = fixture_service
    engine._ensure_index_on_init = False
    public, private = 'public_' + suffix, 'private_' + suffix
    names = [private, public] if private_first else [public, private]
    docs, total = engine.search_multi({'query': 'synthetic question', 'vector': {'value': [1.0, 0.0, 0.0]}},
                                    index_names=names, size=6)
    assert len(docs) == 1 and docs[0]['_id'] == 'public-hit' and total == 1
    assert clients[provider].create_requests == []
    assert engine.search_multi({}, index_names=private) == ([], 0)
    assert private in caplog.text


@pytest.mark.parametrize('suffix,provider', [('s', 'serverless'), ('p', 'paas')])
def test_concurrent_create_validates_winner_mapping(fixture_service, suffix, provider):
    _, engine, clients = fixture_service
    private = 'private_' + suffix
    clients[provider].races.add(private)
    assert engine.search_multi({}, index_names=private) == ([], 0)
    assert engine.has_build_index[private] is True
    assert private in engine._impls
    assert any(call.kwargs['index'] == private for call in clients[provider].indices.get_mapping.call_args_list)


def test_failed_mapping_guard_does_not_cache_binding(fixture_service):
    _, engine, clients = fixture_service
    clients['serverless'].maps['private_s'] = {'properties': {}}
    for _ in range(2):
        with pytest.raises(RuntimeError, match='native KNN'):
            engine.search_multi({}, index_names='public_s,private_s')
        assert 'private_s' not in engine._impls and 'private_s' not in engine.has_build_index
    clients['serverless'].maps['private_s'] = engine._build_mapping()
    assert engine.search_multi({}, index_names='private_s') == ([], 0)


def test_auto_create_does_not_update_existing_mapping(fixture_service):
    _, engine, clients = fixture_service
    mapping = engine._build_mapping()
    del mapping['properties']['title']
    clients['serverless'].maps['existing_s'] = mapping
    assert engine.search_multi({}, index_names='existing_s') == ([], 0)
    assert not clients['serverless'].indices.put_mapping.called
    assert clients['serverless'].create_requests == []


def test_online_query_failure_keeps_other_index(fixture_service, caplog):
    _, engine, clients = fixture_service
    clients['serverless'].maps['private_s'] = engine._build_mapping()
    clients['serverless'].failed_queries.add('private_s')
    docs, _ = engine.search_multi({'query': 'synthetic question'}, index_names='private_s,public_s')
    assert [doc['_id'] for doc in docs] == ['public-hit']
    assert 'private_s' in caplog.text


@pytest.mark.parametrize('operation', ['insert', 'update', 'get', 'delete'])
def test_crud_also_creates_exact_missing_index(fixture_service, operation):
    _, engine, clients = fixture_service
    if operation == 'insert':
        engine.insert({'_id': 'fixture', 'title': 'sample'}, index_names='private_s')
    elif operation == 'update':
        engine.update('fixture', {'title': 'sample'}, index_names='private_s')
    else:
        getattr(engine, operation)('fixture', index_names='private_s')
    assert [item['index'] for item in clients['serverless'].create_requests] == ['private_s']
    assert not clients['paas'].create_requests


def test_creation_failure_is_visible_and_not_cached(fixture_service):
    _, engine, clients = fixture_service
    clients['serverless'].denied.add('private_s')
    for _ in range(2):
        with pytest.raises(ApiError):
            engine.search_multi({}, index_names='private_s,public_s')
        assert 'private_s' not in engine._impls and 'private_s' not in engine.has_build_index
    clients['serverless'].denied.clear()
    assert engine.search_multi({}, index_names='private_s') == ([], 0)


def test_cached_index_removed_is_created_again(fixture_service):
    _, engine, clients = fixture_service
    assert engine.search_multi({}, index_names='private_s') == ([], 0)
    del clients['serverless'].maps['private_s']
    docs, _ = engine.search_multi({}, index_names='public_s,private_s')
    assert [doc['_id'] for doc in docs] == ['public-hit']
    assert [item['index'] for item in clients['serverless'].create_requests] == ['private_s', 'private_s']


def test_cached_exists_transport_failure_keeps_query_fallback(fixture_service, caplog):
    _, engine, clients = fixture_service
    clients['serverless'].indices.exists.side_effect = RuntimeError('synthetic HEAD unavailable')
    docs, _ = engine.search_multi({}, index_names='public_s')
    assert [doc['_id'] for doc in docs] == ['public-hit']
    assert 'existence check failed' in caplog.text
