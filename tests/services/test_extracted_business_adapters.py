"""Preserve language fallback and upstream request behavior after extraction."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize('rule', [('__label__ja', 1.0), None])
def test_language_rule_precedes_unchanged_model_fallback(monkeypatch, rule):
    from kdb.multilingual import detection
    from kdb.multilingual import runtime
    model = Mock()
    model.predict.return_value = (['__label__en'], [0.75])
    monkeypatch.setattr(runtime, 'model', model)
    monkeypatch.setattr(detection, 'rule_based_language_detection', lambda text: rule)
    result = detection.detect_language('sample')
    if rule:
        assert result == {'lang': 'japanese', 'confidence': 1.0, 'label': '__label__ja'}
        model.predict.assert_not_called()
    else:
        assert result == {'lang': 'english', 'confidence': 0.75, 'label': '__label__en'}
        model.predict.assert_called_once_with('sample', k=1)


@pytest.mark.parametrize('status', [200, 503])
def test_fastgpt_transport_and_http_error_contract(monkeypatch, status):
    from kdb.retrieval.providers import fastgpt
    from kdb.entrypoints.http.fastgpt_proxy import app as service
    calls = []
    response = SimpleNamespace(status_code=status, json=lambda: {'responseData': []})
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return response
    monkeypatch.setattr(fastgpt.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(service, 'CONFIG', {'knowledge_base_url': 'https://upstream.invalid/test'})
    if status == 200:
        assert asyncio.run(service.query_remote_service('sample', 'synthetic-key')) == {'responseData': []}
    else:
        with pytest.raises(HTTPException) as caught:
            asyncio.run(service.query_remote_service('sample', 'synthetic-key'))
        assert caught.value.status_code == 503
        assert caught.value.detail == '远程服务请求失败'
    assert calls == [('https://upstream.invalid/test', {
        'headers': {'Authorization': 'Bearer synthetic-key', 'Content-Type': 'application/json'},
        'json': {'stream': False, 'detail': True, 'messages': [{'role': 'user', 'content': 'sample'}]},
    })]
