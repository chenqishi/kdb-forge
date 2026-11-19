import copy
from types import SimpleNamespace
import pytest
from kdb.retrieval.ingestion.conflict_jobs import DedupJob
from kdb.retrieval.ingestion.conflict_store import fingerprint, validate_index


def row(identifier, day=1, **kw):
    return {'_id': identifier, 'data_type': 'qa', 'title': '提款到账时间', 'content': '通常两周到账',
            'insert_time': f'2026-11-{day:02d} 00:00:00', 'del_flag': 0, **kw}


class Store:
    index = 'test-kb'
    def __init__(self, rows):
        self.rows = {r['_id']: copy.deepcopy(r) for r in rows}
        self.changes = []
        self.interface = SimpleNamespace(process_one_data=lambda r, **k: r.update(indexes=[{'text': r['content'], 'embedding': [1]}]) or True)
    def recall(self, r, limit):
        return [copy.deepcopy(x) for x in self.rows.values() if x['_id'] != r['_id'] and not x.get('del_flag') and x['data_type'] == r['data_type']][:limit]
    def read(self, identifier):
        return copy.deepcopy(self.rows.get(identifier))
    def patch(self, old, fields):
        assert fingerprint(old) == fingerprint(self.rows[old['_id']])
        self.rows[old['_id']].update(copy.deepcopy(fields))
        self.changes.append((old['_id'], fields))
    def insert(self, r):
        r = dict(r, _id='inserted')
        r.pop('_offline', None)
        self.rows['inserted'] = r
        return r


class Models:
    usage = {}
    def __init__(self, relation='duplicate'):
        self.relation = relation
    def rerank(self, current, rows):
        return [0.9] * len(rows)
    def judge(self, current, candidate):
        return {'relation': self.relation, 'scope_confirmed': True, 'scope_kind': 'timeless_fact', 'evidence': {'current': current['content'], 'related': candidate['content']}}
    def resolve(self, current, candidate, evidence):
        return {'title': candidate['title'], 'content': current['content']}


def test_record_only_different_progress_and_type_scope():
    store = Store([row('old'), row('new', 2), row('segment', data_type='segment')])
    result = DedupJob(store, Models('different')).run([row('new', 2)])
    assert result['failed'] == 0
    assert store.rows['new']['similarity_info'] == []
    assert store.rows['new']['dedup_check']['status'] == 'complete'
    assert 'dedup_check' not in store.rows['segment']
    assert all(r['del_flag'] == 0 for r in store.rows.values())


@pytest.mark.parametrize('policy,deleted', [('keep_new', 'old'), ('keep_old', 'new')])
def test_duplicate_policy_uses_age_and_repeated_batch_is_safe(policy, deleted):
    store = Store([row('old'), row('new', 2)])
    report = DedupJob(store, Models()).run([row('old'), row('new', 2)], policy=policy)
    assert report['failed'] == 0
    assert store.rows[deleted]['del_flag'] == 1
    assert sum(r['del_flag'] == 0 for r in store.rows.values()) == 1


@pytest.mark.parametrize('policy', ['keep_new', 'keep_old'])
def test_conflicts_update_old_and_reset_review(policy):
    store = Store([row('old', content='通常三周到账', audit_result=1), row('new', 2)])
    result = DedupJob(store, Models('conflict')).run([row('new', 2)], policy=policy)
    assert result['failed'] == 0
    assert store.rows['old']['content'] == '通常两周到账'
    assert store.rows['old']['audit_result'] == -1
    assert store.rows['old']['indexes'][0]['text'] == '通常两周到账'
    assert store.rows['old']['del_flag'] == 0


def test_offline_no_delete_before_insert_and_failure_preserves_old():
    store = Store([row('old')])
    incoming = row('local', 2, _offline=True)
    report = DedupJob(store, Models()).run([incoming], policy='keep_new')
    assert report['failed'] == 0
    assert store.changes == []
    assert report['offline_records'][0]['similarity_info'][0]['related_id'] == 'old'
    def broken(r):
        raise RuntimeError('insert failed')
    store.insert = broken
    report = DedupJob(store, Models()).run([incoming], policy='keep_new', insert_new=True)
    assert report['failed'] == 1
    assert store.rows['old']['del_flag'] == 0


def test_offline_insertion_then_old_deleted():
    store = Store([row('old')])
    report = DedupJob(store, Models()).run([row('local', 2, _offline=True)], policy='keep_new', insert_new=True)
    assert report['failed'] == 0
    assert store.rows['old']['del_flag'] == 1
    assert store.rows['inserted']['del_flag'] == 0
    assert report['offline_records'] == []


def test_offline_same_batch_duplicate_skips_older_output():
    store = Store([])
    report = DedupJob(store, Models()).run([row('a', _offline=True), row('b', _offline=True)], policy='keep_new')
    assert report['failed'] == 0
    assert report['offline_records'][0]['dedup_action'] == 'skip'
    assert report['offline_records'][1]['dedup_action'] == 'retain'


def test_dry_run_and_bad_scope():
    store = Store([row('old'), row('new', 2)])
    result = DedupJob(store, Models()).run([row('new', 2)], policy='keep_new', dry_run=True)
    assert result['failed'] == 0
    assert store.changes == []
    for index in ['', 'a,b', '*', '_all']:
        with pytest.raises(ValueError):
            validate_index(index)


def test_older_selected_conflict_cannot_overwrite_newer_answer():
    store = Store([row('old', 1, content='通常三周到账'), row('new', 2)])
    report = DedupJob(store, Models('conflict')).run([store.read('old')], policy='keep_old')
    assert report['failed'] == 0
    assert store.rows['new']['content'] == '通常两周到账'
    assert store.rows['old']['content'] == '通常两周到账'
    assert store.rows['old']['dedup_check']['status'] == 'pending'
    assert report['results'][0]['needs_recheck']


def test_explicit_round_preserves_unseen_prior_relations():
    store = Store([row('old'), row('new', 2, similarity_info=[{'related_id': 'unseen', 'relation': 'overlap'}])])
    job = DedupJob(store, Models())
    result = job.analyze(store.read('new'))
    result['scope'] = 'explicit_candidates'
    job.apply(result)
    assert {r['related_id'] for r in store.rows['new']['similarity_info']} == {'old', 'unseen'}
    assert store.rows['new']['dedup_check']['status'] == 'partial'


def test_conflict_uses_real_preparation_without_mutating_snapshot(tmp_path, monkeypatch):
    import numpy as np
    from kdb.retrieval.application import search_index_data_interface as module
    monkeypatch.setattr(module, 'EmbeddingTools', lambda *a: SimpleNamespace(text2embedding=lambda text: np.array([1., 0.])))
    config = tmp_path / 'config.json'
    config.write_text('{}')
    interface = module.SearchDataInterface(search_engine=SimpleNamespace(), config_path=str(config))
    store = Store([row('old', 1, content='通常三周到账', audit_result=1, keywords=['到账'],
                       ext_info={'from_file_name': 'test'}, _seq_no=4, _primary_term=1),
                   row('new', 2, keywords=['到账'])])
    store.interface = interface
    result = DedupJob(store, Models('conflict')).run([store.read('new')], policy='keep_new')
    assert result['failed'] == 0
    assert store.rows['old']['content'] == '通常两周到账'
    assert store.rows['old']['ext_info'] == {'from_file_name': 'test'}
    assert store.rows['old']['content_embedding'] == [1., 0.]
    assert store.rows['old']['indexes']


def test_malformed_evidence_and_multimodal_failure_never_delete():
    store = Store([row('old', content='通常三周到账', multimodal_contents=[{'type': 'text', 'text': '三周'}]), row('new', 2)])
    report = DedupJob(store, Models('conflict')).run([store.read('new')], policy='keep_new')
    assert report['failed'] == 1
    assert store.rows['old']['content'] == '通常三周到账'
    assert store.rows['old']['del_flag'] == 0
    assert store.rows['new']['dedup_check']['status'] == 'failed'
