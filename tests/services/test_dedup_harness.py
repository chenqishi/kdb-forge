import json
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from kdb.entrypoints.http.retrieval.dedup_routes import register_dedup_routes
from kdb.retrieval.application.dedup_tools import DedupHarness


def test_harness_disabled_invisible():
    app = FastAPI()
    register_dedup_routes(app, config={})
    assert TestClient(app).post('/knowledge_dedup/mcp', json={}).status_code == 404


def test_server_identity_admin_leader_scope_and_mutation_gate(monkeypatch):
    calls = []
    monkeypatch.setenv('DEDUP_ADMIN_TEST_TOKEN', 'test-secret')
    principal = {'token_env': 'DEDUP_ADMIN_TEST_TOKEN', 'is_admin': True, 'role': 'leader', 'indices': ['kb']}
    app = FastAPI()
    register_dedup_routes(app, config={'enabled': True, 'principals': [principal]}, job_factory=lambda i: calls.append(i))
    client = TestClient(app)
    headers = {'Authorization': 'Bearer test-secret'}
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}
    assert client.post('/knowledge_dedup/mcp', json=request).status_code == 403
    listed = client.post('/knowledge_dedup/mcp', json=request, headers=headers).json()['result']['tools']
    assert len(listed) == 6
    assert client.post('/knowledge_dedup/mcp', json=request, headers={**headers, 'Origin': 'https://untrusted.invalid'}).status_code == 403
    request.update(method='tools/call', params={'name': 'knowledge_dedup_run', 'arguments': {'index': 'other', 'data_type': 'qa'}})
    assert client.post('/knowledge_dedup/mcp', json=request, headers=headers).json()['result']['isError']
    request['params']['arguments'] = {'index': 'kb', 'data_type': 'qa', 'dry_run': False}
    assert client.post('/knowledge_dedup/mcp', json=request, headers=headers).json()['result']['isError']
    request['params']['arguments']['is_admin'] = True
    assert client.post('/knowledge_dedup/mcp', json=request, headers=headers).json()['result']['isError']
    assert calls == []
    principal['role'] = 'customer'
    assert client.post('/knowledge_dedup/mcp', json=request, headers=headers).status_code == 403


def test_select_returns_estimate_and_closes_scan():
    closed = []
    def scan(*a, **kw):
        try:
            for i in range(3):
                yield {'_id': str(i), 'data_type': 'qa', 'content': '到账两周', 'title_embedding': [1, 2]}
        finally:
            closed.append(True)
    job = SimpleNamespace(limit=60, store=SimpleNamespace(scan=scan))
    harness = DedupHarness({'enabled': True}, lambda index: job)
    result = harness.call('knowledge_dedup_select', {'index': 'kb', 'data_type': 'qa', 'max_records': 2},
                          {'role': 'leader', 'is_admin': True, 'indices': ['kb']})
    assert result['selection_truncated']
    assert len(result['records']) == 2
    assert 'title_embedding' not in result['records'][0]
    assert result['estimate']['estimated']
    assert closed == [True]
