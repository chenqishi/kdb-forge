"""Merged features through the real ES8 client, with only transport IO replaced."""
import copy
import hashlib
from types import MappingProxyType, SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock
from elastic_transport import ApiResponseMeta, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse
from fastapi.testclient import TestClient
import numpy as np
import pytest
import kdb.services.forge_compat.api.knowledge_routes as routes
from kdb.services.forge_compat.api.app import app
from kdb.services.forge_compat.repository import KnowledgeRepository
from kdb.services.forge_compat.adapter import KnowledgeService
from kdb.retrieval.engines.es8_client_router import IndexClientRouter
from kdb.services.forge_compat.engine import RoutedLegacyEngine

def embed_text(text):
    return np.array([value + 1.0 for value in hashlib.sha256(text.encode()).digest()[:3]])

@pytest.fixture
def es8_stack(monkeypatch):
    state = SimpleNamespace(calls=[], documents={}, search_hits={})

    def perform_request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        parts = url.path.strip('/').split('/')
        host, index = (node.host, parts[0])
        state.calls.append({'host': host, 'method': method, 'path': url.path, 'params': parse_qs(url.query), 'body': copy.deepcopy(body)})
        if len(parts) == 3 and parts[1] == '_update':
            key = (host, index, parts[2])
            assert key in state.documents or body.get('doc_as_upsert')
            state.documents.setdefault(key, {}).update(copy.deepcopy(body['doc']))
            response = {'result': 'updated'}
        elif len(parts) == 3 and parts[1] == '_doc' and (method == 'GET'):
            key = (host, index, parts[2])
            response = {'_id': parts[2], 'found': key in state.documents, '_source': copy.deepcopy(state.documents.get(key, {}))}
        elif len(parts) == 3 and parts[1] == '_doc' and (method == 'DELETE'):
            del state.documents[host, index, parts[2]]
            response = {'result': 'deleted'}
        elif parts[-1] == '_refresh':
            response = {'_shards': {'successful': 1, 'failed': 0}}
        elif parts[-1] == '_mapping':
            response = {index: {'mappings': {}}}
        elif parts[-1] == '_search':
            hits = copy.deepcopy(state.search_hits.get(host, []))
            response = {'hits': {'total': {'value': len(hits), 'relation': 'eq'}, 'hits': hits}}
        else:
            raise AssertionError(f'Unexpected ES request: {method} {target}')
        return TransportApiResponse(ApiResponseMeta(200, '1.1', HttpHeaders({'x-elastic-product': 'Elasticsearch'}), 0, node), response)
    monkeypatch.setattr(Transport, 'perform_request', perform_request)
    router = IndexClientRouter(config={'providers': {'serverless': {'hosts': ['http://serverless.example:9200']}, 'paas': {'hosts': ['http://paas.example:9200']}}, 'default_provider': 'serverless', 'index_routes': {'idx_b': 'paas'}})
    engine = RoutedLegacyEngine(router=router, index_name='idx_a', vector_fields={'indexes_embedding': 3}, ensure_index=False)
    service = KnowledgeService(KnowledgeRepository(engine=engine), Mock(text2embedding=Mock(side_effect=embed_text)), multimodal_prefix='https://files/')
    state.service = service
    state.router = router
    yield state
    router.close()

@pytest.mark.parametrize('config', [{}, {'check_duplicate': False, 'is_need_llm': True, 'category_service_url': 'https://category.example'}])
def test_positional_service_config_survives_merge(es8_stack, config):
    service = KnowledgeService(es8_stack.service._repo, es8_stack.service._embedding, 'idx_a', 'https://files/', MappingProxyType(config))
    assert service.check_duplicate is config.get('check_duplicate', True)
    assert service.is_need_llm is config.get('is_need_llm', False)
    assert service.category_service_url == config.get('category_service_url', '')
    assert service._legacy_config == config
    assert not es8_stack.calls

def test_duplicate_config_is_rejected(es8_stack):
    with pytest.raises(TypeError, match='both positionally and by keyword'):
        KnowledgeService(es8_stack.service._repo, es8_stack.service._embedding, 'idx_a', '', {}, legacy_config={})

@pytest.mark.parametrize('patch, regenerate, expected', [({'title': 'new'}, True, {'old', 'new', 'alias', 'custom', 'diagram'}), ({'title': '', 'synonyms_title': [], 'content': ''}, True, {'custom', 'diagram'}), ({'synonyms_title': ['new alias']}, True, {'old', 'new alias', 'custom', 'diagram'}), ({'title': 'new', 'indexes': [{'text': 'explicit'}]}, True, {'explicit'}), ({'title': 'new'}, False, {'old', 'alias', 'custom', 'diagram'})])
def test_update_preserves_unrelated_indexes(es8_stack, patch, regenerate, expected):
    key = ('paas.example', 'idx_b', 'doc-1')
    es8_stack.documents[key] = {'title': 'old', 'synonyms_title': ['old', 'alias'], 'content': 'answer', 'title_embedding': embed_text('old').tolist(), 'content_embedding': embed_text('answer').tolist(), 'indexes': [{'text': text, 'embedding': embed_text(text).tolist()} for text in ['old', 'alias', 'custom', 'diagram']], 'image_indexes': [{'text': 'diagram'}]}
    original = copy.deepcopy(patch)
    assert es8_stack.service.update('doc-1', patch, index_name='idx_b', regenerate_embedding=regenerate)
    assert patch == original
    stored = es8_stack.documents[key]
    assert {item['text'] for item in stored['indexes']} == expected
    if patch.get('title') == '':
        assert stored['title_embedding'] is None and stored['content_embedding'] is None
    if 'indexes' in patch or not regenerate:
        assert len([call for call in es8_stack.calls if not call['path'].endswith('/_mapping')]) == 1

def test_title_update_without_stored_document_does_not_write(es8_stack):
    with pytest.raises(ValueError, match='stored document'):
        es8_stack.service.update('missing', {'title': 'new'}, index_name='idx_b', regenerate_embedding=True)
    assert [call['method'] for call in es8_stack.calls] == ['GET']
