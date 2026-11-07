"""Original search scenarios with the real SDK and a batch-aware transport boundary."""
import copy
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from elastic_transport import Transport
from elastic_transport._transport import TransportApiResponse
import pytest

_path = Path(__file__).resolve().parents[1] / "baseline_forge/tests/test_es8_merge_regressions.py"
_spec = importlib.util.spec_from_file_location("_forge_native_transport_reference", _path)
_reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_reference)


@pytest.fixture
def batch_stack(monkeypatch):
    # Keep the original constructor/configuration and response fixture unchanged.
    original_fixture = _reference.es8_stack.__wrapped__(monkeypatch)
    state = next(original_fixture)
    search_transport = Transport.perform_request
    state.physical_requests = []

    def transport(transport, method, target, *, body=None, headers=None, **kwargs):
        node = transport.node_pool.all()[0].config
        url = urlsplit(target)
        state.physical_requests.append({"host": node.host, "method": method, "path": url.path,
                                        "params": parse_qs(url.query), "body": copy.deepcopy(body)})
        if url.path != "/_msearch":
            return search_transport(transport, method, target, body=body, headers=headers, **kwargs)
        # Real ES msearch accepts alternating metadata/query NDJSON records.
        records = body
        if isinstance(records, bytes):
            records = records.decode()
        if isinstance(records, str):
            records = [json.loads(line) for line in records.splitlines() if line.strip()]
        assert isinstance(records, list) and len(records) % 2 == 0
        responses = []
        for metadata, query in zip(records[::2], records[1::2]):
            response = search_transport(
                transport, "POST", f"/{metadata['index']}/_search",
                body=query, headers=headers, **kwargs,
            )
            responses.append(response.body)
        return TransportApiResponse(response.meta, {"responses": responses})

    monkeypatch.setattr(Transport, "perform_request", transport)
    yield state
    next(original_fixture, None)


@pytest.mark.parametrize("method,query", [("search_text", "question"), ("search_text_multi", ["question"])])
def test_original_results_and_parameters_through_native_batch(batch_stack, method, query):
    for index, host in [("idx_a", "serverless.example"), ("idx_b", "paas.example")]:
        batch_stack.search_hits[host] = [{"_index": index, "_id": "same-id", "_score": 2., "_source": {
            "title": "question", "title_embedding": _reference.embed_text("question").tolist(),
            "content": "[multimodal_prefix]report.pdf", "audit_result": 2,
            "multimodal_contents": [{"type": "file", "path": "report.pdf", "fileName": "a b.pdf"}],
        }}]
    docs, total = getattr(batch_stack.service, method)(query, index_name=["idx_a", "idx_b"], size=4)
    assert len(docs) == total == 2
    assert {doc["_index"] for doc in docs} == {"idx_a", "idx_b"}
    assert all(doc["similarity"] > 0 and doc["content"] == "https://files/report.pdf?filename=a%20b.pdf" for doc in docs)
    # Count actual batch requests separately from the fixture's logical search records.
    assert len(batch_stack.physical_requests) == 2
    for request, index, host in zip(batch_stack.physical_requests, ("idx_a", "idx_b"),
                                    ("serverless.example", "paas.example")):
        assert request["host"] == host and request["path"] == "/_msearch"
        assert request["params"] == {"max_concurrent_searches": ["2"]}
        metadata_a, bm25, metadata_b, vector = request["body"]
        assert metadata_a == metadata_b == {"index": index}
        assert bm25["size"] == vector["size"] == 4
        assert "knn" not in str(bm25["query"])
        assert "script_score" not in str(vector["query"])
        knn = vector["query"]["bool"]["should"][0]["nested"]["query"]["knn"]
        assert knn["field"] == "indexes.embedding"
        assert knn["query_vector"] == _reference.embed_text("question").tolist()
        assert knn["k"] == 4 and knn["num_candidates"] == 100
        assert knn["filter"] == bm25["query"]["bool"]["must"][0]
        assert all(field in str(knn["filter"]) for field in ("del_flag", "audit_result", "quality_level"))
