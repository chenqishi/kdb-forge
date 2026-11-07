"""Source filtering differential against the real old engine; native API boundary only."""
import copy
from unittest.mock import Mock

import pytest

from kdb.retrieval.engines.es_search_interface import EsSearchInterfaceOri
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from tests.retrieval.test_es8_interface import routed_clients

SOURCE = {'title': 'title', 'content': 'answer', 'synonyms_title': ['synonym'],
          'title_embedding': [1, 0, 0], 'content_embedding': [0, 0, 1],
          'indexes': [{'text': 'title', 'embedding': [1, 0, 0]}, {'text': 'synonym', 'embedding': [0, 1, 0]}],
          'image_indexes': [{'text': 'picture', 'embedding': [0, 1, 0]}],
          'ext_info': {'from_file_name': 'original.pdf'}, 'audit_result': 2, 'del_flag': 0,
          'primary_category': {'category_ids': ['MX']}, 'extra_business_field': {'keep': True}}
QUERY = {'query': 'synonym', 'vector': {'value': [0, 1, 0]}, 'attribute': [{'data_type': ['qa']}]}


def inner_queries(node):
    found = []
    if isinstance(node, dict):
        nested = node.get('nested')
        if isinstance(nested, dict) and nested.get('inner_hits'):
            found.append(nested)
        for child in node.values():
            found.extend(inner_queries(child))
    elif isinstance(node, list):
        for child in node:
            found.extend(inner_queries(child))
    return found


def filtered_hit(index, identity, body):
    source = copy.deepcopy(SOURCE)
    for path in (body.get('_source') or {}).get('excludes', []):
        if '.' in path:
            parent, field = path.split('.', 1)
            for item in source.get(parent, []):
                item.pop(field, None)
        else:
            source.pop(path, None)
    hit = {'_index': index, '_id': identity, '_score': 1 if inner_queries(body) else 20, '_source': source}
    for nested in inner_queries(body):
        path = nested['path']; offset = 1 if path == 'indexes' else 0
        entry = SOURCE[path][offset]
        includes = nested['inner_hits']['_source']['includes']
        relative = {field: copy.deepcopy(value) for field, value in entry.items() if path + '.' + field in includes}
        hit.setdefault('inner_hits', {})[nested['inner_hits']['name']] = {'hits': {'hits': [{
            '_nested': {'field': path, 'offset': offset}, '_source': relative}]}}
    return hit


def native_response(**kwargs):
    plan = kwargs.get('searches') or kwargs.get('body')
    if isinstance(plan, list):
        replies = [native_response(index=h['index'], **b) for h, b in zip(plan[::2], plan[1::2])]
        return {'responses': replies}
    body = copy.deepcopy(plan) if isinstance(plan, dict) else {key: copy.deepcopy(value) for key, value in kwargs.items() if key != 'index'}
    if kwargs.get('source_excludes'):
        body['_source'] = {'excludes': kwargs['source_excludes']}
    vector = bool(inner_queries(body))
    ids = ['shared'] if vector else ['shared', 'bm25-only']
    return {'_shards': {'failed': 0}, 'hits': {'total': {'value': 5 if vector else 7},
        'hits': [filtered_hit(kwargs['index'], identity, body) for identity in ids]}}


def legacy_engine(client):
    old = EsSearchInterfaceOri.__new__(EsSearchInterfaceOri)
    old.es = client; old.index_name = 'qa_one'; old.has_build_index = {'qa_one': True}
    old.vector_fields = {'indexes_embedding': 3}; old.recall_mode = 'dual'; old.auto_update_mapping = False
    return old


def test_dual_source_and_rerank_equal_real_legacy(routed_clients):
    new, clients = routed_clients; client = clients['serverless']
    client.msearch = Mock(side_effect=native_response)
    old_client = Mock(); old_client.msearch.side_effect = native_response
    old = legacy_engine(old_client)
    before = copy.deepcopy(QUERY)
    old_docs, old_total = old.search_multi(copy.deepcopy(QUERY), index_names=['qa_one'], size=10)
    new_docs, new_total = new.search_multi(QUERY, index_names=['qa_one'], size=10)
    assert QUERY == before and (new_docs, new_total) == (old_docs, old_total)
    by_id = {d['_id']: d for d in new_docs}
    assert by_id['shared']['indexes'][1]['embedding'] == [0, 1, 0]
    assert 'embedding' not in by_id['shared']['indexes'][0]
    assert all('embedding' not in x for x in by_id['bm25-only']['indexes'])
    assert all(d['title_embedding'] == SOURCE['title_embedding'] and d['content_embedding'] == SOURCE['content_embedding']
               and d['extra_business_field'] == SOURCE['extra_business_field'] for d in new_docs)
    reranker = SearchDataInterface.__new__(SearchDataInterface)
    scores = [reranker._cal_similarity('synonym', [0, 1, 0], d, use_synonyms=True) for d in new_docs]
    assert scores == [1, 0]


def test_fallback_retains_old_source_policy(routed_clients):
    new, clients = routed_clients; client = clients['serverless']
    client.msearch = Mock(side_effect=RuntimeError('batch unavailable'))
    client.search = Mock(side_effect=native_response)
    docs, _ = new.search_multi(copy.deepcopy(QUERY), index_names=['qa_one'], size=10)
    for call in client.search.call_args_list:
        assert call.kwargs['source_excludes'] == ['indexes.embedding', 'image_indexes.embedding']
    assert len(client.search.call_args_list) == 2
    assert docs[0]['indexes'][1]['embedding'] == [0, 1, 0]
    assert all('embedding' not in x for x in docs[1]['indexes'])


@pytest.mark.parametrize('mode,vector', [('legacy', True), ('single', True), ('bm25', True), ('vector', True), ('dual', False)])
def test_full_source_modes(routed_clients, mode, vector):
    new, clients = routed_clients; client = clients['serverless']
    client.search = Mock(side_effect=native_response)
    query = copy.deepcopy(QUERY)
    if not vector:
        query.pop('vector')
    docs, _ = new.search_multi(query, index_names=['qa_one'], size=10, recall_mode=mode)
    assert all(d['indexes'] == SOURCE['indexes'] and d['image_indexes'] == SOURCE['image_indexes'] for d in docs)
    assert 'source_excludes' not in client.search.call_args.kwargs


@pytest.mark.parametrize('path', ['indexes', 'image_indexes'])
def test_dynamic_inner_source_paths(routed_clients, path):
    new, _ = routed_clients
    query = new._build_knn_clause([0, 1, 0], vector_field=path + '.embedding', k=2, with_inner_hits=True)
    assert query['nested']['inner_hits']['_source']['includes'] == [path + '.text', path + '.embedding']
    hit = filtered_hit('qa_one', 'shared', {'query': query, '_source': {'excludes': ['indexes.embedding', 'image_indexes.embedding']}})
    doc = copy.deepcopy(hit['_source']); new._restore_inner_embeddings(hit, doc)
    offset = 1 if path == 'indexes' else 0
    assert doc[path][offset]['embedding'] == SOURCE[path][offset]['embedding']
    other = 'image_indexes' if path == 'indexes' else 'indexes'
    assert all('embedding' not in x for x in doc[other])


@pytest.mark.parametrize('path,offset', [('indexes', -1), ('indexes', 9), ('indexes', '1'), ('image_indexes', None), ('unknown', 0)])
def test_invalid_inner_offsets(routed_clients, path, offset):
    new, _ = routed_clients; doc = copy.deepcopy(SOURCE); before = copy.deepcopy(doc)
    hit = {'inner_hits': {'best_index': {'hits': {'hits': [{'_nested': {'field': path, 'offset': offset},
        '_source': {'embedding': [9, 9, 9]}}]}}}}
    new._restore_inner_embeddings(hit, doc)
    assert doc == before


def test_merge_preserves_namespaces_and_existing(routed_clients):
    new, _ = routed_clients
    target = {'indexes': [{'text': 'same'}, {'text': 'fixed', 'embedding': [1, 0, 0]}],
              'image_indexes': [{'text': 'same'}, {'url': 'keep'}], 'ext_info': {'keep': True}}
    other = {'indexes': [{'text': 'same', 'embedding': [0, 1, 0]}, {'text': 'fixed', 'embedding': [9, 9, 9]}],
             'image_indexes': [{'text': 'same', 'embedding': [0, 0, 1]}, {'url': 'keep', 'embedding': [9, 9, 9]}]}
    new._merge_index_embeddings(target, other)
    assert target['indexes'] == [{'text': 'same', 'embedding': [0, 1, 0]}, {'text': 'fixed', 'embedding': [1, 0, 0]}]
    assert target['image_indexes'] == [{'text': 'same', 'embedding': [0, 0, 1]}, {'url': 'keep'}]
    assert target['ext_info'] == {'keep': True}
