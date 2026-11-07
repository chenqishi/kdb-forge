from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
部分分片失败（ES Serverless 的 task_cancelled_exception）不能被当成功。

背景：阿里云 ES Serverless 会取消跑得慢的分片任务，HTTP 仍是 200，
只是 `_shards.failed>0`、hits 少一个分片的量。search_after 的游标只认最后一条 hit，
被取消分片在这一段的文档就永久跳过——实测 mercado_local 10007 条导出成 6675 条，
而且每次少的条数都不一样。
"""

import os
import sys

import pytest


from kdb.shared.clients.es_http_client import EsHttpClient
from kdb.shared.clients.es_http_client import MIN_PAGE_SIZE
from kdb.shared.clients.es_http_client import SHARD_RETRY_TIMES
from kdb.shared.clients.es_http_client import PartialShardFailure
from kdb.shared.clients.es_http_client import shard_failure_reason


def _client(monkeypatch, responses):
    """responses: list of (status, payload)，按调用顺序返回；记录每次请求体。"""
    es = EsHttpClient(hosts=['http://es.example'])
    calls = []
    seq = list(responses)

    def fake_request(method, path, body=None, raw_body=None):
        calls.append({'path': path, 'body': body})
        return seq.pop(0)

    monkeypatch.setattr(es, '_request', fake_request)
    monkeypatch.setattr('kdb.shared.clients.es_http_client.time.sleep', lambda *_: None)
    return es, calls


_OK_SHARDS = {'total': 3, 'successful': 3, 'failed': 0}
_BAD_SHARDS = {'total': 3, 'successful': 2, 'failed': 1,
               'failures': [{'shard': 0, 'reason': {'type': 'task_cancelled_exception'}}]}


def _hits(ids):
    return {'timed_out': False, '_shards': _OK_SHARDS,
            'hits': {'hits': [{'_id': i, '_source': {'title': i}, 'sort': [i]} for i in ids]}}


def _partial_hits(ids):
    page = _hits(ids)
    page['_shards'] = _BAD_SHARDS
    return page


def test_shard_failure_reason_detects_cancelled_shard():
    assert shard_failure_reason(_partial_hits(['a'])) is not None
    assert shard_failure_reason(_hits(['a'])) is None


def test_shard_failure_reason_detects_timeout():
    payload = _hits(['a'])
    payload['timed_out'] = True
    assert 'timed_out' in shard_failure_reason(payload)


def test_search_retries_partial_page_then_succeeds(monkeypatch):
    es, calls = _client(monkeypatch, [
        (200, _partial_hits(['a'])),
        (200, _hits(['a', 'b', 'c'])),
    ])
    payload = es.search('mercado_local', {'size': 3})
    assert [h['_id'] for h in payload['hits']['hits']] == ['a', 'b', 'c']
    assert len(calls) == 2


def test_search_raises_when_shards_keep_failing(monkeypatch):
    es, _ = _client(monkeypatch, [(200, _partial_hits(['a']))] * 3)
    with pytest.raises(PartialShardFailure):
        es.search('mercado_local', {'size': 3}, retries=2)


def test_search_allow_partial_opt_out(monkeypatch):
    es, _ = _client(monkeypatch, [(200, _partial_hits(['a']))])
    assert es.search('mercado_local', {}, allow_partial=True)['hits']['hits']


def test_count_raises_on_partial_shards(monkeypatch):
    """count 偏小最致命：导出对账拿它当基准，静默少捞就永远对得上。"""
    es, _ = _client(monkeypatch, [
        (200, {'count': 6675, '_shards': _BAD_SHARDS}),
    ] * 2)
    with pytest.raises(PartialShardFailure):
        es.count('mercado_local', {}, retries=1)


def test_count_retries_then_returns_full_count(monkeypatch):
    es, _ = _client(monkeypatch, [
        (200, {'count': 6675, '_shards': _BAD_SHARDS}),
        (200, {'count': 10007, '_shards': _OK_SHARDS}),
    ])
    assert es.count('mercado_local', {}) == 10007


def test_iter_search_after_does_not_skip_docs_on_partial_page(monkeypatch):
    """整页重试时游标不能前移，否则被取消分片那一段的文档永远捞不到。"""
    es, calls = _client(monkeypatch, [
        (200, _hits(['a', 'b'])),
        (200, _partial_hits(['c'])),      # 第二页被取消，重试
        (200, _hits(['c', 'd'])),
        (200, _hits([])),
    ])
    got = [doc_id for doc_id, _ in es.iter_search_after('mercado_local', {}, ['title'],
                                                        page_size=2)]
    assert got == ['a', 'b', 'c', 'd']
    # 重试那次的 search_after 仍是第一页最后一条，没有跟着部分结果前移
    assert calls[1]['body']['search_after'] == ['b']
    assert calls[2]['body']['search_after'] == ['b']


def test_iter_search_after_halves_page_size_when_retry_exhausted(monkeypatch):
    attempts = SHARD_RETRY_TIMES + 1  # 一页把重试全耗光才会折半
    es, calls = _client(monkeypatch, [
        (200, _partial_hits(['a']))] * attempts + [
        (200, _hits(['a', 'b'])),
        (200, _hits([])),
    ])
    got = [doc_id for doc_id, _ in es.iter_search_after('mercado_local', {}, ['title'],
                                                        page_size=200)]
    assert got == ['a', 'b']
    assert calls[0]['body']['size'] == 200
    assert calls[attempts]['body']['size'] == 100


def test_iter_search_after_raises_instead_of_silently_losing_rows(monkeypatch):
    es, _ = _client(monkeypatch, [(200, _partial_hits(['a']))] * 40)
    with pytest.raises(PartialShardFailure):
        list(es.iter_search_after('mercado_local', {}, ['title'], page_size=MIN_PAGE_SIZE))
