"""Native batch behavior through the real old-project ES8 engine and Router.

Only the external ES API is mocked. No live write or service restart is used.
"""
import copy
import json
from unittest.mock import Mock

import pytest

from test_es8_interface import routed_clients


@pytest.mark.parametrize("mode,size,budget,count", [("dual", 10, 5, 4), ("vector", 10, 10, 2), ("dual", 3, 1, 4)])
def test_native_batch_preserves_payload_and_merge(routed_clients, mode, size, budget, count):
    engine, clients = routed_clients
    client = clients["serverless"]
    source = {"title_embedding": [1, 0, 0], "content_embedding": [0, 1, 0],
              "indexes": [{"text": "synonym", "embedding": [1, 0, 0]}],
              "image_indexes": [{"text": "image", "embedding": [0, 1, 0]}],
              "ext_info": {"from_file_name": "sample.txt"}}
    replies = []
    for index in ["qa_one", "qa_two"]:
        for route in range(2 if mode == "dual" else 1):
            replies.append({"_shards": {"failed": 0}, "hits": {"total": {"value": 7}, "hits": [
                {"_index": index, "_id": "same", "_score": route + 1, "_source": copy.deepcopy(source)}]}})
    client.msearch = Mock(return_value={"responses": replies})
    query = {"query": "hello", "vector": {"value": [1, 0, 0]},
             "attribute": [{"quality_level": ["high"], "audit_result": [1, 2], "category_ids": ["MX"]}]}
    before = copy.deepcopy(query)
    docs, total = engine.search_multi(query, index_names=["qa_one", "qa_two"], size=size, recall_mode=mode)
    assert query == before
    assert [d["_index"] for d in docs] == ["qa_one", "qa_two"] and total == 14
    assert all(d["score"] == 1 and all(d[field] == source[field] for field in source) for d in docs)
    batch = client.msearch.call_args.kwargs
    assert batch["max_concurrent_searches"] == 2 and len(batch["searches"]) == count * 2
    for header, body in zip(batch["searches"][::2], batch["searches"][1::2]):
        assert body["size"] == budget
        if mode == "dual":
            assert body["_source"] == {"excludes": ["indexes.embedding", "image_indexes.embedding"]}
        else:
            assert "_source" not in body
        serialized = json.dumps(body)
        assert "primary_category.category_ids" in serialized and "del_flag" in serialized
        assert "script_score" not in serialized
        if '"knn"' in serialized:
            knn = body["query"]["bool"]["should"][0]["nested"]["query"]["knn"]
            assert knn["k"] == budget and knn["num_candidates"] == max(100, budget * 10)
    assert not any(name == "search" for name, _ in client.calls)


def test_interleaved_providers_keep_order(routed_clients):
    engine, clients = routed_clients
    docs, total = engine.search_multi({"query": "hello", "vector": {"value": [1, 0, 0]}},
                                    index_names="qa_a,archive_b,qa_c", size=4)
    assert [d["_index"] for d in docs] == ["qa_a", "archive_b", "qa_c"] and total == 3
    batches = [kwargs for name, kwargs in clients["serverless"].calls if name == "msearch"]
    assert [[h["index"] for h in b["searches"][::2]] for b in batches] == [["qa_a", "qa_a"], ["qa_c", "qa_c"]]
    assert len([c for c in clients["paas"].calls if c[0] == "msearch"]) == 1


@pytest.mark.parametrize("retry_transport_failure", [False, True])
def test_partial_retry_retains_success_and_final_hits(routed_clients, monkeypatch, caplog, retry_transport_failure):
    engine, clients = routed_clients
    monkeypatch.setattr("knowledge_interface_tools.es8_search_interface.time.sleep", Mock())
    client = clients["serverless"]
    good = {"_shards": {"failed": 0}, "hits": {"total": 1, "hits": [
        {"_index": "qa_a", "_id": "good", "_score": 1, "_source": {"title": "good"}}]}}
    partial = {"_shards": {"failed": 1}, "hits": {"total": 1, "hits": [
        {"_index": "qa_b", "_id": "partial", "_score": 1, "_source": {"title": "partial"}}]}}
    client.msearch = Mock(side_effect=[{"responses": [good, partial]},
        RuntimeError("retry network down") if retry_transport_failure else {"responses": [partial]},
        {"responses": [partial]}])
    docs, _ = engine.search_multi({"query": "hello"}, index_names="qa_a,qa_b", recall_mode="bm25")
    assert [d["_id"] for d in docs] == ["good", "partial"]
    calls = client.msearch.call_args_list
    assert len(calls) == (2 if retry_transport_failure else 3)
    assert [c.kwargs["searches"][0]["index"] for c in calls] == ["qa_a"] + ["qa_b"] * (len(calls) - 1)
    assert "partial recall retained" in caplog.text
    client.search = Mock(return_value=partial)
    with pytest.raises(RuntimeError, match="分片查询失败"):
        engine.search({}, index_names="qa_b")
    assert client.search.call_count == 3


@pytest.mark.parametrize("failure", ["transport", "cardinality", "item"])
def test_online_batch_failure_falls_back_visibly(routed_clients, caplog, failure):
    engine, clients = routed_clients
    client = clients["serverless"]
    good = {"_shards": {"failed": 0}, "hits": {"total": 1, "hits": [
        {"_index": "qa_b", "_id": "b", "_score": 1, "_source": {"title": "good"}}]}}
    if failure == "transport":
        client.msearch = Mock(side_effect=RuntimeError("synthetic batch unavailable"))
    else:
        client.msearch = Mock(return_value={"responses": [good] if failure == "cardinality" else [
            {"error": {"type": "index_not_found_exception"}}, good]})
    docs, _ = engine.search_multi({"query": "hello"}, index_names="qa_a,qa_b", recall_mode="bm25")
    assert [d["_index"] for d in docs] == (["qa_b"] if failure == "item" else ["qa_a", "qa_b"])
    assert "failed" in caplog.text
    assert len([c for c in client.calls if c[0] == "search"]) == (0 if failure == "item" else 2)


def test_compat_body_preserves_parameters_and_validates(routed_clients):
    engine, clients = routed_clients
    client = clients["serverless"]
    client.msearch = Mock(return_value={"responses": [{"hits": {"hits": []}}, {"hits": {"hits": []}}]})
    body = [{"index": "qa_a", "routing": "tenant"},
            {"query": {"match_all": {}}, "size": 0, "from": 2, "sort": [{"rank": "asc"}],
             "track_total_hits": True, "_source": False},
            {"index": "qa_b"}, {"query": {"match_all": {}}, "size": 1}]
    engine._msearch_with_shard_check(body)
    assert client.msearch.call_args.kwargs["searches"] == body
    assert client.msearch.call_count == 1
    for invalid in [[{}], [{"index": "qa_a,archive_b"}, {}], [{}, []]]:
        with pytest.raises(ValueError):
            engine._msearch_with_shard_check(invalid)
    assert client.msearch.call_count == 1
