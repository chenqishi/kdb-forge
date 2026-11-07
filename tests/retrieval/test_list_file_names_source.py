"""HTTP request through real business code; only aggregation is replaced."""
import asyncio
from unittest.mock import Mock

import pytest

from tests.retrieval.test_es8_autocreate import fixture_service
from tests.retrieval.test_es8_autocreate import post_query


@pytest.mark.parametrize("index_name", ["public_s", "public_p"])
@pytest.mark.parametrize("params,source_type", [
    ({}, None),
    ({"from_type_norm": None}, None),
    ({"from_type_norm": ""}, None),
    ({"from_type_norm": " \t "}, None),
    ({"from_type_norm": "document"}, "document"),
    ({"from_type_norm": "html"}, "html"),
    ({"from_type_norm": "manual"}, "manual"),
    ({"from_type_norm": " auto_learning "}, "auto_learning"),
    ({"from_type_norm": "unknown_source"}, "unknown_source"),
])
def test_http_source_filter(fixture_service, monkeypatch, index_name, params, source_type):
    service, engine, _ = fixture_service
    buckets = [] if source_type == "unknown_source" else [
        {"key": "a.pdf", "doc_count": 3, "sub": {"by_type": {"qa": 2, "segment": 1}}}]
    aggregate = Mock(return_value=buckets)
    monkeypatch.setattr(engine, "agg_terms", aggregate)
    request = dict(params, index_name=index_name, keyword="a*?", size=50)
    response = asyncio.run(post_query(service, "/list_file_names", request))
    assert response.status_code == 200
    wire = response.json()
    assert wire == {
        "success": True,
        "values": [] if not buckets else [
            {"value": "a.pdf", "doc_count": 3, "type_count": {"qa": 2, "segment": 1}}],
        "total_count": len(buckets),
        "message": "共 %d 个来源文件" % len(buckets),
    }
    filters = [{"term": {"del_flag": 0}}]
    if source_type:
        filters.append({"term": {"from_type_norm": source_type}})
    filters.append({"wildcard": {"ext_info.from_file_name.keyword": {
        "value": r"*a\*\?*", "case_insensitive": True}}})
    aggregate.assert_called_once_with(
        index_name, {"bool": {"must": filters}}, "ext_info.from_file_name.keyword",
        size=50, sub_aggs={"by_type": {"terms": {"field": "data_type", "size": 10}}})
    # Listing all sources must not expand preview/delete scope.
    delete_query = service.SEARCH_DATA_INTERFACE._build_file_query(["a.pdf"])
    assert {"terms": {"from_type_norm": ["document", "html", "manual"]}} in delete_query["bool"]["must"]


@pytest.mark.parametrize("source_type", [[], ["document"], {}, 12, True])
def test_invalid_source_type(fixture_service, monkeypatch, source_type):
    service, engine, _ = fixture_service
    aggregate = Mock()
    monkeypatch.setattr(engine, "agg_terms", aggregate)
    response = asyncio.run(post_query(service, "/list_file_names", {
        "index_name": "public_s", "from_type_norm": source_type}))
    assert response.status_code == 422
    aggregate.assert_not_called()
