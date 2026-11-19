from kdb.retrieval.ingestion.conflict_check import compare_candidates


def test_duplicate_evidence_checked_and_type_boundaries():
    current = {'_id': 'new', 'data_type': 'qa', 'content': '一般两周'}
    candidates = [{'_id': 'a', 'data_type': 'qa', 'content': '时效两周内'},
                  {'_id': 'b', 'data_type': 'segment', 'content': '一般两周'}]
    result = compare_candidates(current, candidates, lambda c, rows: [0.8],
        lambda c, r: {'relation': 'duplicate', 'reason': '时效一致',
                      'evidence': {'current': '两周', 'related': '两周'}})
    assert result['status'] == 'complete'
    assert result['candidate_count'] == 1
    assert result['similarity_info'][0]['related_id'] == 'a'
    assert result['similarity_info'][0]['relation'] == 'duplicate'


def test_unverifiable_quote_is_uncertain_and_errors_are_visible():
    current = {'data_type': 'qa', 'content': '七天'}
    candidate = {'_id': 'x', 'data_type': 'qa', 'content': '三十天'}
    result = compare_candidates(current, [candidate], lambda c, rows: [0.7],
        lambda c, r: {'relation': 'conflict', 'evidence': {'current': '虚构', 'related': '三十天'}})
    assert result['similarity_info'][0]['relation'] == 'uncertain'
    def broken(c, rows):
        raise RuntimeError('unavailable')
    failed = compare_candidates(current, [candidate], broken, lambda c, r: {})
    assert failed['status'] == 'failed'
    assert failed['errors'][0]['stage'] == 'rerank'


def test_different_is_not_persisted():
    result = compare_candidates({'data_type': 'qa'}, [{'_id': 'x', 'data_type': 'qa'}],
        lambda c, rows: [0.9], lambda c, r: {'relation': 'different'})
    assert result['judged_count'] == 1
    assert result['similarity_info'] == []


def test_increment_batch_uses_same_type_and_reports_truncation():
    from kdb.retrieval.ingestion.conflict_check import check_batch
    record = {'_id': 'new', 'data_type': 'qa', 'content': '两周'}
    candidates = [{'_id': str(i), 'data_type': 'qa', 'content': '两周'} for i in range(3)]
    candidates += [{'_id': 'segment', 'data_type': 'segment', 'content': '两周'}]
    result = check_batch([record], candidates, lambda r, rows, limit: rows[:limit],
                         lambda r, rows: [0.9] * len(rows),
                         lambda r, row: {'relation': 'duplicate', 'evidence': {'current': '两周', 'related': '两周'}},
                         limit=2)[0]
    assert result['status'] == 'complete'
    assert result['truncated'] is True
    assert len(result['similarity_info']) == 2


def test_rerank_preserves_candidate_order_and_usage(monkeypatch):
    from kdb.retrieval.ingestion import conflict_models
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'output': {'results': [{'index': 1, 'relevance_score': 0.9},
                                           {'index': 0, 'relevance_score': 0.2}]},
                    'usage': {'total_tokens': 12}}
    monkeypatch.setattr(conflict_models.requests, 'post', lambda *a, **kw: Response())
    usage = {}
    scores = conflict_models.rerank_candidates({'title': '问题'}, [{'title': 'a'}, {'title': 'b'}],
                  endpoint='https://example.invalid', api_key='test', usage=usage)
    assert scores == [0.2, 0.9]
    assert usage == {'calls': 1, 'total_tokens': 12}


def test_policy_conflict_requires_shared_effective_scope():
    current = {'data_type': 'qa', 'content': '德国仓可以发货'}
    old = {'_id': 'old', 'data_type': 'qa', 'content': '德国仓不可以发货'}
    judge = lambda *a: {'relation': 'conflict', 'scope_confirmed': True, 'scope_kind': 'policy',
                        'evidence': {'current': '德国仓可以发货', 'related': '德国仓不可以发货'}}
    result = compare_candidates(current, [old], lambda *a: [.9], judge)
    assert result['similarity_info'][0]['relation'] == 'uncertain'
    assert result['similarity_info'][0]['evidence']['current'] == current['content']


def test_rerank_chunks_long_items_without_omission(monkeypatch):
    from kdb.retrieval.ingestion import conflict_models
    calls = []
    def request(query, docs, **kw):
        calls.append((query, docs))
        assert len(query.encode()) <= 120
        assert all(len(d.encode()) <= 120 for d in docs)
        assert sum(len(query.encode()) + len(d.encode()) for d in docs) <= 480
        return [.7] * len(docs)
    monkeypatch.setattr(conflict_models, '_rerank_request', request)
    record = {'content': '中文长文本' * 120}
    scores = conflict_models.rerank_candidates(record, [record, record], endpoint='test', api_key='test',
                                              max_input_bytes=120, max_request_bytes=480)
    assert scores == [.7, .7]
    assert len(calls) > 2


def test_bad_evidence_shape_is_uncertain_instead_of_model_success_or_crash():
    result = compare_candidates({'data_type': 'qa', 'content': '两周'},
        [{'_id': 'old', 'data_type': 'qa', 'content': '两周'}], lambda *a: [.9],
        lambda *a: {'relation': 'duplicate', 'evidence': [{'current': '两周', 'related': '两周'}]})
    assert result['status'] == 'complete'
    assert result['similarity_info'][0]['relation'] == 'uncertain'
    assert result['similarity_info'][0]['evidence'] == {}
