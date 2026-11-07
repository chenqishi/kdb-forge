# -*- coding:utf8 -*-

"""统一引擎维护更新对 update_by_query 各种返回结构的处理（迁移原审核回归）。

回归点：阿里云 ES Serverless 即使传了 wait_for_completion=true，单次运行超过 60 秒
也会自动转异步，只回 `{"task": "<node>:<id>"}`——task 是**字符串**。
原代码写的是 `result.get("task", {}).get("status", result)`，直接
`AttributeError: 'str' object has no attribute 'get'`，整个索引审核失败、0 条更新。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_auto_audit_update_by_query.py')

import importlib.util
import os
import sys

import pytest
from knowledge_interface_tools.es_maintenance import run_native_update

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
_spec = importlib.util.spec_from_file_location(
    'timing_auto_audit_kg', os.path.join(REPO, 'control_script', 'timing_auto_audit_kg.py'))
aa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aa)

WRITE_SIZE_ERROR = {
    'type': 'status_exception',
    'reason': ('write_size blocked, limited by [MAX_WRITE_SIZE_PER_REQUEST]'
               '[write.max_size_per_request] threshold:[15728640] try acquire [23992548]'),
}

BODY = {'query': {'match_all': {}}, 'script': {'source': 'ctx._source.audit_result = 2'}}


class _FakeEs(object):
    """按预设脚本依次返回 update_by_query 的响应；tasks.get 按 task_id 返回。"""

    def __init__(self, responses, task_results=None):
        self._responses = list(responses)
        self._task_results = task_results or {}
        self.scroll_sizes = []
        self.tasks = self

    def update_by_query(self, index, body, scroll_size, **kwargs):
        self.scroll_sizes.append(scroll_size)
        return self._responses.pop(0)

    def get(self, task_id):
        return self._task_results[task_id]


def _processor(es):
    return es


def test_同步扁平返回():
    p = _processor(_FakeEs([{'updated': 30, 'total': 30, 'failures': []}]))
    out = run_native_update(p, {'index': 'idx', 'body': BODY}, scroll_size=30, client_api=7)
    assert out['updated'] == 30
    assert out['failures'] == []


def test_写入超限时减半重试():
    es = _FakeEs([
        {'task': {'status': {'updated': 0, 'total': 0}}, 'error': WRITE_SIZE_ERROR},
        {'updated': 12, 'total': 12, 'failures': []},
    ])
    out = run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=30, client_api=7)
    assert es.scroll_sizes == [30, 15]
    assert out['updated'] == 12
    assert es.scroll_sizes[-1] == 15


def test_转异步时轮询task而不是崩掉():
    """核心回归：task 是字符串。"""
    es = _FakeEs(
        [{'task': 'node1:88548096'}],
        {'node1:88548096': {'completed': True,
                            'task': {'status': {'updated': 5000, 'total': 5000}},
                            'response': {'updated': 5000, 'total': 5000, 'failures': []}}},
    )
    out = run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=15, client_api=7)
    assert out['updated'] == 5000
    assert out['failures'] == []


def test_异步任务带写入超限错误时仍能减半重试():
    """轮询回来的结构里带 error，不能因为有 response 就把 error 丢掉。"""
    es = _FakeEs(
        [{'task': 'node1:1'}, {'updated': 7, 'total': 7, 'failures': []}],
        {'node1:1': {'completed': True,
                     'task': {'status': {'updated': 0, 'total': 0}},
                     'response': {'updated': 0, 'total': 0, 'failures': []},
                     'error': WRITE_SIZE_ERROR}},
    )
    out = run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=30, client_api=7)
    assert es.scroll_sizes == [30, 15]
    assert out['updated'] == 7


def test_减到最小仍超限就显式报错而不是静默返回0():
    es = _FakeEs([{'task': {'status': {'updated': 0, 'total': 0}}, 'error': WRITE_SIZE_ERROR}] * 12)
    with pytest.raises(RuntimeError):
        run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=1, client_api=7)


def test_非写入超限的错误直接抛出():
    es = _FakeEs([{'task': {'status': {'updated': 0, 'total': 0}},
                   'error': {'type': 'mapper_parsing_exception', 'reason': 'bad field'}}])
    with pytest.raises(RuntimeError):
        run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=30, client_api=7)


def test_写入失败会被记录并停止():
    es = _FakeEs([{'updated': 3, 'total': 3, 'failures': [{'id': 'x', 'cause': 'boom'}]}])
    with pytest.raises(RuntimeError, match='bulk_failure'):
        run_native_update(es, {'index': 'idx', 'body': BODY}, scroll_size=30, client_api=7)
