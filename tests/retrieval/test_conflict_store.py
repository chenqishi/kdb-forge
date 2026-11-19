import copy
from types import SimpleNamespace
import pytest
from kdb.retrieval.ingestion.conflict_store import KnowledgeStore, fingerprint


def test_patch_snapshot_and_version_precondition(tmp_path):
    row = {'_id': 'id', 'data_type': 'qa', 'content': 'old', 'audit_result': -1, 'del_flag': 0}
    calls = []
    client = SimpleNamespace(get=lambda **kw: {'_id': 'id', '_source': {k:v for k,v in row.items() if k!='_id'}, '_seq_no': 4, '_primary_term': 2},
        update=lambda **kw: calls.append(kw) or {'result': 'updated'})
    store = KnowledgeStore(SimpleNamespace(engine=SimpleNamespace(get_client_by_index=lambda index: client)), 'kb', tmp_path/'journal.jsonl')
    store.patch(dict(row), {'del_flag': 1})
    assert calls[0]['if_seq_no'] == 4
    assert calls[0]['if_primary_term'] == 2
    assert calls[0]['index'] == 'kb'
    assert (tmp_path/'journal.jsonl').stat().st_size > 0
    stale = dict(row)
    row['audit_result'] = 1
    with pytest.raises(RuntimeError, match='changed'):
        store.patch(stale, {'del_flag': 1})
    assert len(calls) == 1


def test_scan_increment_resets_after_content_change_and_includes_unaudited_only():
    row = {'_id': 'a', 'data_type': 'qa', 'content': 'old', 'del_flag': 0}
    row['dedup_check'] = {'status': 'complete', 'fingerprint': fingerprint(row)}
    calls = []
    engine = SimpleNamespace(scroll_search=lambda query, **kw: calls.append((query, kw)) or iter([row]))
    store = KnowledgeStore(SimpleNamespace(engine=engine), 'kb')
    assert list(store.scan('qa', since='2026-10-19', unaudited=True)) == []
    row['content'] = 'changed'
    assert len(list(store.scan('qa'))) == 1
    assert calls[0][0]['attribute'] == {'data_type': 'qa', 'del_flag': 0, 'audit_result': -1}
    assert calls[0][0]['insert_time'] == ['2026-10-19', None]


def test_online_recall_no_score_or_platform_or_audit_filter():
    calls = []
    records = [{'_id': 'self', 'data_type': 'qa'}, {'_id': 'candidate', 'data_type': 'qa'}]
    interface = SimpleNamespace(embedding_tools=SimpleNamespace(text2embedding=lambda t: [1.0]),
                                search_data=lambda query, **kw: calls.append((query, kw)) or records)
    store = KnowledgeStore(interface, 'kb')
    assert store.recall({'_id': 'self', 'data_type': 'qa', 'content': 'text'})[0]['_id'] == 'candidate'
    assert calls[0][0]['attribute'] == {'data_type': 'qa', 'del_flag': 0}
    assert calls[0][1] == {'size': 61, 'index_names': 'kb'}
    assert 'min_score' not in calls[0][0]


from tests.retrieval.test_es8_interface import routed_clients


@pytest.mark.parametrize('size,expected_k', [(61, 61), (None, 10)])
def test_native_recall_reaches_requested_topn(routed_clients, size, expected_k):
    engine, clients = routed_clients
    engine.search({'query': '到账', 'vector': {'value': [1, 0, 0]},
                   'attribute': {'data_type': 'qa'}}, size=size, index_names='qa_one')
    calls = [kw for name, kw in clients['serverless'].calls if name == 'search']
    should = calls[-1]['query']['bool']['should']
    vector = next(clause['nested']['query']['knn'] for clause in should if 'nested' in clause)
    assert vector['k'] == expected_k
    assert vector['num_candidates'] >= expected_k


@pytest.mark.parametrize('scroll', [False, True])
def test_incomplete_es_response_cannot_mark_dedup_complete(routed_clients, monkeypatch, scroll):
    from unittest.mock import Mock
    import kdb.retrieval.engines.es8_search_interface as module
    engine, clients = routed_clients
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: None)
    client = clients['serverless']
    client.search = Mock(return_value={'_shards': {'failed': 1}, '_scroll_id': 'partial-scroll', 'hits': {'hits': []}})
    client.clear_scroll = Mock()
    query = {'attribute': {'data_type': 'qa'}}
    with pytest.raises(RuntimeError, match='分片查询失败'):
        if scroll:
            list(engine.scroll_search(query, index_names='qa_one'))
        else:
            engine.search(query, index_names='qa_one')
