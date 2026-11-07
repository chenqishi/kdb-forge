"""Forge input protocol through the unchanged published native-batch API."""
import copy
from unittest.mock import Mock

import numpy as np
import pytest

from test_es8_interface import routed_clients
from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService


@pytest.mark.parametrize("method,query", [
    ("search_text", "hello"), ("search_text_multi", ["hello"]),
    ("search_data_by_query", "hello"), ("search_data_by_multi_query", ["hello"]),
])
def test_index_list_keeps_cross_provider_results_with_native_batch(routed_clients, method, query):
    engine, clients = routed_clients
    for provider, index in [("serverless", "qa_one"), ("paas", "archive_one")]:
        engine.get_client_by_index(index)  # The existing router creates fake clients lazily.
        hit = {"_index": index, "_id": "same-id", "_score": 2., "_source": {
            "title": "hello", "title_embedding": [1., 0., 0.],
            "content": "[multimodal_prefix]report.pdf", "audit_result": 2,
            "multimodal_contents": [{"type": "file", "path": "report.pdf", "fileName": "a b.pdf"}],
        }}
        reply = {"_shards": {"failed": 0}, "hits": {"total": 1, "hits": [hit]}}
        clients[provider].msearch = Mock(return_value={"responses": [copy.deepcopy(reply), copy.deepcopy(reply)]})
    embedding = Mock(text2embedding=Mock(return_value=np.array([1., 0., 0.])))
    service = KnowledgeService(KnowledgeRepository(engine), embedding, multimodal_prefix="https://files/")
    argument = "index_names" if method.startswith("search_data") else "index_name"
    docs, total = getattr(service, method)(query, **{argument: ["qa_one", "archive_one"]}, size=4)
    assert len(docs) == total == 2
    assert {doc["_index"] for doc in docs} == {"qa_one", "archive_one"}
    assert all(doc["similarity"] > 0 and doc["content"] == "https://files/report.pdf?filename=a%20b.pdf" for doc in docs)
    for provider, index in [("serverless", "qa_one"), ("paas", "archive_one")]:
        clients[provider].msearch.assert_called_once()
        searches = clients[provider].msearch.call_args.kwargs["searches"]
        assert [header["index"] for header in searches[::2]] == [index, index]
        assert "knn" not in str(searches[1]["query"])
        assert "script_score" not in str(searches[3]["query"])
        assert searches[3]["query"]["bool"]["should"][0]["nested"]["query"]["knn"]["query_vector"] == [1., 0., 0.]
        assert not any(name == "search" for name, _ in clients[provider].calls)
