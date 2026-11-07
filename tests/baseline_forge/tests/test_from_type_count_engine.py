"""Exact native count uses the real ES8 client/router and fails closed."""

import copy
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from elastic_transport import ApiResponseMeta, ConnectionError, HttpHeaders, Transport
from elastic_transport._transport import TransportApiResponse
from elasticsearch import ApiError

from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


def complete_count(count=13, total=3):
    return {"count": count, "_shards": {"total": total, "successful": total, "failed": 0}}


@pytest.fixture
def count_stack(monkeypatch):
    state = SimpleNamespace(calls=[], response=complete_count(), failure=None, allow_init=False)

    def perform_request(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        state.calls.append({"host": node.host, "method": method, "path": unquote(url.path),
                            "params": parse_qs(url.query), "body": copy.deepcopy(body)})
        if url.path.endswith("/_count"):
            if state.failure == "connection":
                raise ConnectionError("unavailable provider")
            if state.failure:
                status, error_type = state.failure
                response = {"error": {"type": error_type, "reason": "provider failure"},
                            "status": status}
            else:
                status, response = 200, copy.deepcopy(state.response)
        else:
            # Only the explicit ensure=True constructor test permits writes.
            assert state.allow_init, "count must never ensure/create/read mapping/search"
            assert url.path == "/market_a"
            if method == "HEAD":
                status, response = 404, None
            elif method == "PUT":
                status, response = 200, {"acknowledged": True, "index": "market_a"}
            else:
                raise AssertionError("unexpected initialization request")
        return TransportApiResponse(
            ApiResponseMeta(status, "1.1", HttpHeaders({"x-elastic-product": "Elasticsearch"}), 0, node),
            response,
        )

    monkeypatch.setattr(Transport, "perform_request", perform_request)
    router = IndexClientRouter(config={
        "providers": {
            "serverless": {"hosts": ["http://serverless.example:9200"], "max_retries": 0},
            "paas": {"hosts": ["http://paas.example:9200"], "max_retries": 0},
        },
        "default_provider": "serverless",
        "index_routes": {"payoneer": "paas", "missing_paas": "paas"},
    })

    def build_engine(ensure_index=False):
        return RoutedLegacyEngine(router=router, index_name="market_a",
                                  vector_fields={"indexes_embedding": 3}, ensure_index=ensure_index)

    state.engine = build_engine()
    state.build_engine = build_engine
    yield state
    router.close()


@pytest.mark.parametrize("index, host", [
    ("market_a", "serverless.example"),
    ("payoneer", "paas.example"),
    ("PaYoneer", "paas.example"),  # Routing may normalize its key; the ES index stays literal.
])
def test_count_routes_one_literal_index_and_preserves_raw_dsl(index, host, count_stack):
    query = {"bool": {"filter": [
        {"term": {"quality_level": "high"}},
        {"term": {"from_type": "chat_auto"}},
        {"range": {"insert_time": {"gte": "2026-09-01 00:00:00", "lte": "2026-10-08 23:59:59"}}},
    ]}}
    original = copy.deepcopy(query)
    assert count_stack.engine.count_by_query(index, query, require_complete=True) == 13
    assert query == original
    assert count_stack.calls == [{
        "host": host, "method": "POST", "path": f"/{index}/_count",
        "params": {"ignore_unavailable": ["false"], "allow_no_indices": ["false"],
                   "expand_wildcards": ["none"]},
        "body": {"query": original},
    }]


@pytest.mark.parametrize("count", [0, 17, 10_001, 123_456])
def test_complete_count_returns_exact_integer_without_search_hit_limit(count, count_stack):
    count_stack.response = complete_count(count)
    assert count_stack.engine.count_by_query("market_a", {"match_all": {}}, require_complete=True) == count
    assert len(count_stack.calls) == 1


@pytest.mark.parametrize("failure", [
    (404, "index_not_found_exception"),
    (401, "security_exception"),
    (403, "security_exception"),
    (503, "unavailable_shards_exception"),
])
def test_http_failure_is_propagated_without_fallback_or_creation(failure, count_stack):
    count_stack.failure = failure
    with pytest.raises(ApiError) as error:
        count_stack.engine.count_by_query("missing_paas", {"match_all": {}}, require_complete=True)
    assert error.value.status_code == failure[0]
    assert len(count_stack.calls) == 1
    assert count_stack.calls[0]["host"] == "paas.example"
    assert count_stack.calls[0]["path"] == "/missing_paas/_count"


def test_transport_failure_is_propagated(count_stack):
    count_stack.failure = "connection"
    with pytest.raises(ConnectionError):
        count_stack.engine.count_by_query("market_a", {"match_all": {}}, require_complete=True)
    assert len(count_stack.calls) == 1


@pytest.mark.parametrize("response", [
    {},
    {"_shards": {"total": 1, "successful": 1, "failed": 0}},
    complete_count(None), complete_count(True), complete_count("13"),
    complete_count(13.0), complete_count(-1),
    {"count": 13}, {"count": 13, "_shards": None},
    {"count": 13, "_shards": []},
    {"count": 13, "_shards": {"total": 1, "successful": 1}},
    complete_count(13, total=0),
    {"count": 13, "_shards": {"total": 3, "successful": 2, "failed": 1}},
    {"count": 13, "_shards": {"total": 3, "successful": 2, "failed": 0}},
    {"count": 13, "_shards": {"total": 3, "successful": 4, "failed": 0}},
    {"count": 13, "_shards": {"total": "3", "successful": 3, "failed": 0}},
    {"count": 13, "_shards": {"total": 3, "successful": True, "failed": 0}},
    {"count": 13, "_shards": {"total": 3, "successful": 3, "failed": -1}},
    dict(complete_count(), timed_out=True),
    dict(complete_count(), timed_out="false"),
    dict(complete_count(), terminated_early=True),
    dict(complete_count(), failures=[{"reason": "failure"}]),
    dict(complete_count(), error={"reason": "failure"}),
    {"count": 13, "_shards": {"total": 3, "successful": 3, "failed": 0,
                             "failures": [{"reason": "failure"}]}},
])
def test_incomplete_or_malformed_response_never_becomes_a_successful_count(response, count_stack):
    count_stack.response = response
    with pytest.raises(RuntimeError, match="ES count"):
        count_stack.engine.count_by_query("market_a", {"match_all": {}}, require_complete=True)
    assert len(count_stack.calls) == 1


def test_explicit_false_completion_flags_are_valid(count_stack):
    count_stack.response = dict(complete_count(0), timed_out=False, terminated_early=False,
                                failures=[])
    assert count_stack.engine.count_by_query("market_a", {"match_none": {}}, require_complete=True) == 0


def test_count_does_not_ensure_uncached_index_even_when_engine_ensure_is_true(count_stack):
    count_stack.allow_init = True
    engine = count_stack.build_engine(ensure_index=True)
    assert [call["method"] for call in count_stack.calls] == ["HEAD", "PUT"]
    assert set(engine._impls) == {"market_a"}
    count_stack.calls.clear()
    count_stack.allow_init = False
    assert engine.count_by_query("payoneer", {"match_all": {}}, require_complete=True) == 13
    assert set(engine._impls) == {"market_a"}
    assert len(count_stack.calls) == 1
    assert count_stack.calls[0]["path"] == "/payoneer/_count"


@pytest.mark.parametrize("response, expected", [({}, 0), ({"count": 0}, 0), ({"count": "17"}, 17)])
def test_existing_callers_keep_default_count_coercion_without_strict_kwargs(response, expected, count_stack):
    count_stack.response = response
    assert count_stack.engine.count_by_query("market_a", {"match_all": {}}) == expected
    assert count_stack.calls[0]["params"] == {}
    assert len(count_stack.calls) == 1
