from types import SimpleNamespace
import pytest
from kdb.shared.similarity.knowledge import SimilityTools, SimLLMModel
from kdb.retrieval.ingestion.deduplication import find_duplicates
from kdb.shared.clients import structured_llm


def test_fast_same_index_across_platforms_and_type_boundary():
    sim = SimilityTools()
    a = {'title': '开通条件', 'content': '须提供营业执照', 'data_type': 'qa', 'platform': 'one'}
    b = dict(a, platform='two')
    assert sim.is_simility_knowledge(a, b) == 1
    assert sim.is_simility_knowledge(a, dict(b, data_type='segment')) == 0
    calls = []
    interface = SimpleNamespace(process_one_data=lambda row: True, simility_tools=sim,
        search_data=lambda q, **kw: calls.append((q, kw)) or [dict(b, _id='old')])
    assert find_duplicates(interface, dict(a, _id='new'), index_name='kb')[0]['_id'] == 'old'
    assert calls[0][0]['attribute'] == {'data_type': 'qa'}
    assert calls[0][1]['index_names'] == 'kb'


def test_direct_judge_needs_real_quotes(monkeypatch):
    from kdb.shared.similarity import knowledge
    monkeypatch.setattr(knowledge, 'request_json', lambda *a: {'duplicate': True,
        'evidence': {'current': '证据', 'related': '虚构'}})
    assert SimLLMModel().is_simility_knowledge({'content': '证据'}, {'content': '证据'}) == 0


def test_structured_model_usage_and_bad_json(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'choices': [{'message': {'content': 'not json'}}],
                    'usage': {'prompt_tokens': 11, 'completion_tokens': 3, 'total_tokens': 14}}
    monkeypatch.setattr(structured_llm.requests, 'post', lambda *a, **kw: Response())
    usage = {}
    with pytest.raises(ValueError):
        structured_llm.request_json('规则', {}, {'endpoint': 'https://example.invalid', 'api_key': 'test', 'model': 'test'}, usage)
    assert usage['total_tokens'] == 14
    assert usage['calls'] == 1
