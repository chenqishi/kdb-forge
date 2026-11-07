"""Aliyun source filtering must preserve ranking, deduplication and updates."""

import copy
import fnmatch
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService, _FallbackSimilityTools
from kdb.es.client_router import IndexClientRouter
from kdb.es.engine import RoutedLegacyEngine


ROOTS = ("title_embedding", "content_embedding")


class FilteredClient:
    """Model stored-source filtering separately from indexed vector docvalues."""

    def __init__(self, filtered=True):
        self.filtered = filtered
        self.calls = []
        self.seq_no = 7
        self.search_version_delta = 0
        self.bulk_conflict = False
        self.document = {
            "title": "same", "content": "same", "data_type": "qa", "platform": "web",
            "del_flag": 0, "audit_result": 1,
            "title_embedding": [1.0, 0.0, 0.0], "content_embedding": [1.0, 0.0, 0.0],
            "indexes": [{"text": "same", "embedding": [1.0, 0.0, 0.0]}],
            "image_indexes": [{"text": "image", "embedding": [0.0, 1.0, 0.0]}],
        }
        self.indices = SimpleNamespace(get_mapping=self.get_mapping, refresh=lambda **kwargs: {})

    def get_mapping(self, **kwargs):
        self.calls.append(("mapping", kwargs))
        return {kwargs["index"]: {"mappings": {"_source": {"excludes": list(ROOTS) if self.filtered else []}}}}

    def stored_source(self):
        return {key: copy.deepcopy(value) for key, value in self.document.items()
                if not self.filtered or key not in ROOTS}

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return {"_index": kwargs["index"], "_id": kwargs["id"], "found": True,
                "_source": self.stored_source(), "_seq_no": self.seq_no, "_primary_term": 1}

    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        source = self.stored_source()
        includes = kwargs.get("source_includes") or []
        excludes = kwargs.get("source_excludes") or []
        if isinstance(includes, str):
            includes = [includes]
        if isinstance(excludes, str):
            excludes = [excludes]
        source = {key: value for key, value in source.items()
                  if (not includes or any(fnmatch.fnmatchcase(key, pattern) for pattern in includes))
                  and not any(fnmatch.fnmatchcase(key, pattern) for pattern in excludes)}
        hit = {"_index": kwargs["index"], "_id": "existing", "_score": 1.0,
               "_seq_no": self.seq_no + self.search_version_delta, "_primary_term": 1}
        if kwargs.get("source") is not False:
            hit["_source"] = source
        fields = {field: [copy.deepcopy(self.document[field])] for field in kwargs.get("docvalue_fields", [])
                  if self.document.get(field) is not None}
        if fields:
            hit["fields"] = fields
        result = {"hits": {"total": {"value": 1}, "hits": [hit]}}
        if kwargs.get("scroll"):
            result["_scroll_id"] = "cursor"
        return result

    def update(self, **kwargs):
        self.calls.append(("update", copy.deepcopy(kwargs)))
        if "if_seq_no" in kwargs:
            assert kwargs["if_seq_no"] == self.seq_no
            assert kwargs["if_primary_term"] == 1
        # ES rebuilds the document from stored source and the patch. Missing
        # root vectors really disappear unless the adapter sends them again.
        self.document = self.stored_source()
        def merge(target, patch):
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = copy.deepcopy(value)
        merge(self.document, kwargs["doc"])
        self.seq_no += 1
        return {"result": "updated"}

    def bulk(self, **kwargs):
        self.calls.append(("bulk", copy.deepcopy(kwargs)))
        header, document = kwargs["operations"]
        if self.bulk_conflict:
            return {"items": [{"update": {"status": 409, "error": {"type": "version_conflict_engine_exception"}}}]}
        self.update(index=header["update"]["_index"], id=header["update"]["_id"],
                    doc=document["doc"], if_seq_no=header["update"]["if_seq_no"],
                    if_primary_term=header["update"]["if_primary_term"])
        return {"items": [{"update": {"status": 200, "result": "updated"}}]}

    def scroll(self, **kwargs):
        self.calls.append(("scroll", kwargs))
        return {"_scroll_id": "cursor", "hits": {"hits": []}}

    def clear_scroll(self, **kwargs):
        self.calls.append(("clear_scroll", kwargs))
        return {"succeeded": True}

    def update_by_query(self, **kwargs):
        self.calls.append(("update_by_query", kwargs))
        return {"updated": 1, "total": 1, "failures": []}


def make_engine(client):
    router = IndexClientRouter(config={"hosts": ["http://es8.example"]},
                               client_factory=lambda config: client)
    return RoutedLegacyEngine(router=router, index_name="idx", vector_fields={"indexes_embedding": 3},
                              ensure_index=False)


def test_native_recall_keeps_legacy_similarity_and_duplicate_detection():
    client = FilteredClient()
    engine = make_engine(client)
    service = KnowledgeService(KnowledgeRepository(engine),
                               Mock(text2embedding=Mock(return_value=np.array([1.0, 0.0, 0.0]))))
    service.simility_tools = _FallbackSimilityTools()
    docs, total = service.search_text("same", condition_dicts=[{"data_type": ["qa"]}])
    assert total == 1 and len(docs) == 1
    assert docs[0]["similarity"] == pytest.approx(1.2)
    duplicates = service.find_duplicates({"_id": "different", "title": "same", "content": "same",
                                          "data_type": "qa", "platform": "web"},
                                         is_need_llm=False)
    assert [doc["_id"] for doc in duplicates] == ["existing"]
    assert not any(method in {"update", "bulk"} for method, _ in client.calls)


@pytest.mark.parametrize("source", [False, {"excludes": ["*embedding*"]},
                                   {"includes": ["title", "content"]},
                                   {"exclude_vectors": True}])
def test_source_projection_does_not_restore_excluded_vectors(source):
    client = FilteredClient()
    engine = make_engine(client)
    result = engine._search_with_shard_check("idx", {"query": {"match_all": {}}, "_source": source})
    assert "docvalue_fields" not in client.calls[-1][1]
    assert not any(field in result["hits"]["hits"][0].get("_source", {}) for field in ROOTS)


def test_bm25_pagination_does_not_request_vectors():
    client = FilteredClient()
    engine = make_engine(client)
    engine.search_multi_by_page({"query": "same"})
    assert "docvalue_fields" not in client.calls[-1][1]


def test_get_restores_vectors_without_modifying_nested_source():
    client = FilteredClient()
    engine = make_engine(client)
    document = engine.get("existing")
    assert all(document[field] == client.document[field] for field in ROOTS)
    assert document["indexes"] == client.document["indexes"]
    assert document["image_indexes"] == client.document["image_indexes"]
    searches = [kwargs for method, kwargs in client.calls if method == "search"]
    assert searches[0]["source"] is False
    assert searches[0]["seq_no_primary_term"] is True


@pytest.mark.parametrize("operation", ["get", "update"])
def test_unrefreshed_vectors_cannot_be_mixed_with_newer_document(operation):
    client = FilteredClient()
    client.search_version_delta = -1
    engine = make_engine(client)
    with pytest.raises(RuntimeError, match="尚未刷新或已被并发修改"):
        if operation == "get":
            engine.get("existing")
        else:
            engine.update("existing", {"audit_result": 2})
    assert not any(method == "update" for method, _ in client.calls)


@pytest.mark.parametrize("patch", [{"audit_result": 2},
                                  {"content_embedding": [0.0, 1.0, 0.0]},
                                  {"title_embedding": None}])
def test_partial_update_preserves_omitted_root_vectors(patch):
    client = FilteredClient()
    previous = copy.deepcopy(client.document)
    engine = make_engine(client)
    original = copy.deepcopy(patch)
    assert engine.update("existing", patch)
    assert patch == original
    for field in ROOTS:
        assert client.document[field] == patch.get(field, previous[field])
    assert client.document["indexes"] == previous["indexes"]
    assert client.document["image_indexes"] == previous["image_indexes"]
    update = [kwargs for method, kwargs in client.calls if method == "update"][0]
    assert update["if_seq_no"] == 7 and update["if_primary_term"] == 1


def test_existing_upsert_preserves_root_vectors():
    client = FilteredClient()
    previous = copy.deepcopy(client.document)
    engine = make_engine(client)
    assert engine.insert({"_id": "existing", "audit_result": 2})
    assert all(client.document[field] == previous[field] for field in ROOTS)


@pytest.mark.parametrize("conflict", [False, True])
def test_bulk_metadata_update_preserves_vectors_and_reports_conflicts(conflict):
    client = FilteredClient()
    previous = copy.deepcopy(client.document)
    client.bulk_conflict = conflict
    engine = make_engine(client)
    result = engine.update_by_query("idx", {"match_all": {}}, {"audit_result": 2}, requests_per_second=0)
    assert result["updated"] == (0 if conflict else 1)
    assert result["version_conflicts"] == (1 if conflict else 0)
    assert result["total"] == 1 and result["failures"] == []
    assert all(client.document[field] == previous[field] for field in ROOTS)
    assert any(method == "clear_scroll" for method, _ in client.calls)
    assert not any(method == "update_by_query" for method, _ in client.calls)


def test_unfiltered_indices_keep_native_update_by_query():
    client = FilteredClient(filtered=False)
    engine = make_engine(client)
    assert engine.update_value("idx", {"audit_result": 2}, [{"del_flag": 0}])
    assert any(method == "update_by_query" for method, _ in client.calls)
    assert not any(method in {"get", "search", "bulk"} for method, _ in client.calls)


def test_filtered_bulk_dotted_update_keeps_source_shape_and_sibling_fields():
    client = FilteredClient()
    client.document["ext_info"] = {"from_page": "old", "from_file_name": "keep.pdf",
                                    "extra": {"keep": 1, "change": 2}}
    engine = make_engine(client)
    result = engine.update_by_query("idx", {"match_all": {}},
                                    {"ext_info.from_page": "new", "ext_info.extra.change": 3},
                                    requests_per_second=0)
    assert result["updated"] == 1
    assert client.document["ext_info"] == {"from_page": "new", "from_file_name": "keep.pdf",
                                           "extra": {"keep": 1, "change": 3}}
    assert "ext_info.from_page" not in client.document
    bulk = next(kwargs for method, kwargs in client.calls if method == "bulk")
    assert bulk["operations"][1]["doc"]["ext_info"] == {"from_page": "new", "extra": {"change": 3}}
    assert all(field in client.document for field in ROOTS)


def test_missing_vector_is_not_invented_and_float32_precision_is_preserved():
    client = FilteredClient()
    del client.document["content_embedding"]
    client.document["title_embedding"] = np.array([0.123456789, 0.333333333, 0.987654321], dtype=np.float32).tolist()
    engine = make_engine(client)
    document = engine.search_by_vector([1.0, 0.0, 0.0], "title_embedding")[0]
    assert "content_embedding" not in document
    assert np.max(np.abs(np.array(document["title_embedding"]) - [0.123456789, 0.333333333, 0.987654321])) < 1e-6


class ClientStatusError(RuntimeError):
    def __init__(self, status_code):
        super().__init__("simulated client failure")
        self.status_code = status_code


@pytest.mark.parametrize("not_found_response", [True, False])
def test_missing_upsert_uses_create_only_then_cas_after_concurrent_creator(not_found_response):
    client = FilteredClient()
    engine = make_engine(client)
    get_existing = client.get
    reads = 0
    previous = copy.deepcopy(client.document)

    def get(**kwargs):
        nonlocal reads
        reads += 1
        if reads == 1:
            if not_found_response:
                return {"_id": kwargs["id"], "found": False}
            raise ClientStatusError(404)
        return get_existing(**kwargs)

    # Another writer creates the document between our GET and create attempt.
    client.get = get
    client.create = Mock(side_effect=ClientStatusError(409))
    patch = {"_id": "existing", "audit_result": 2}
    assert engine.insert(patch)
    assert patch == {"_id": "existing", "audit_result": 2}
    client.create.assert_called_once_with(index="idx", id="existing", document={"audit_result": 2}, refresh=False)
    write = next(kwargs for method, kwargs in client.calls if method == "update")
    assert write["if_seq_no"] == 7 and write["if_primary_term"] == 1
    assert write["doc_as_upsert"] is False
    assert all(client.document[field] == previous[field] for field in ROOTS)
    assert client.document["indexes"] == previous["indexes"]


def test_missing_upsert_create_success_does_not_run_unconditional_update():
    client = FilteredClient()
    client.get = Mock(return_value={"found": False})
    client.create = Mock(return_value={"result": "created"})
    assert make_engine(client).insert({"_id": "new", "audit_result": 2})
    client.create.assert_called_once_with(index="idx", id="new", document={"audit_result": 2}, refresh=False)
    assert not any(method == "update" for method, _ in client.calls)


@pytest.mark.parametrize("failure, expected_calls", [(403, 1), (409, 3), (503, 1)])
def test_missing_upsert_creation_failures_are_not_swallowed_or_retried_forever(failure, expected_calls):
    client = FilteredClient()
    client.get = Mock(return_value={"found": False})
    client.create = Mock(side_effect=ClientStatusError(failure))
    with pytest.raises(ClientStatusError):
        make_engine(client).insert({"_id": "new", "audit_result": 2})
    assert client.create.call_count == expected_calls
    assert not any(method == "update" for method, _ in client.calls)


@pytest.mark.parametrize("partial", [{"timed_out": True}, {"_shards": {"failed": 1}}])
def test_partial_docvalues_response_prevents_single_document_update(partial):
    client = FilteredClient()
    search = client.search
    client.search = lambda **kwargs: dict(search(**kwargs), **partial)
    with pytest.raises(RuntimeError, match="超时或分片失败"):
        make_engine(client).update("existing", {"audit_result": 2})
    assert not any(method == "update" for method, _ in client.calls)


@pytest.mark.parametrize("partial", [{"timed_out": True}, {"_shards": {"failed": 1}}])
@pytest.mark.parametrize("page", ["first", "scroll"])
def test_partial_bulk_input_page_never_reports_complete_and_clears_scroll(partial, page):
    client = FilteredClient()
    method = "search" if page == "first" else "scroll"
    original = getattr(client, method)
    setattr(client, method, lambda **kwargs: dict(original(**kwargs), **partial))
    with pytest.raises(RuntimeError, match="超时或分片失败"):
        make_engine(client).update_by_query("idx", {"match_all": {}}, {"audit_result": 2}, requests_per_second=0)
    assert sum(method == "bulk" for method, _ in client.calls) == (0 if page == "first" else 1)
    assert any(method == "clear_scroll" for method, _ in client.calls)


def test_filtered_bulk_missing_scroll_context_does_not_write():
    client = FilteredClient()
    search = client.search

    def missing_scroll(**kwargs):
        result = search(**kwargs)
        result.pop("_scroll_id", None)
        return result

    client.search = missing_scroll
    with pytest.raises(RuntimeError, match="缺少 scroll 上下文"):
        make_engine(client).update_by_query("idx", {"match_all": {}}, {"audit_result": 2}, requests_per_second=0)
    assert not any(method == "bulk" for method, _ in client.calls)


@pytest.mark.parametrize("filtered", [True, False])
def test_update_value_does_not_claim_success_when_all_documents_conflict(filtered):
    client = FilteredClient(filtered=filtered)
    client.bulk_conflict = True
    client.update_by_query = Mock(return_value={"updated": 0, "total": 1, "version_conflicts": 1, "failures": []})
    assert make_engine(client).update_value("idx", {"audit_result": 2}, [{"del_flag": 0}]) is False


@pytest.mark.parametrize("operation", ["update_value", "update_by_query"])
@pytest.mark.parametrize("partial", [{"timed_out": True}, {"_shards": {"failed": 1}}])
def test_native_batch_partial_result_is_not_reported_as_success(operation, partial):
    client = FilteredClient(filtered=False)
    client.update_by_query = Mock(return_value={"updated": 1, "total": 1, "failures": [], **partial})
    engine = make_engine(client)
    with pytest.raises(RuntimeError, match="超时或分片失败"):
        if operation == "update_value":
            engine.update_value("idx", {"audit_result": 2}, [{"del_flag": 0}])
        else:
            engine.update_by_query("idx", {"match_all": {}}, {"audit_result": 2})


def test_bulk_item_shard_failure_is_not_counted_as_confirmed_update():
    client = FilteredClient()
    client.bulk = Mock(return_value={"items": [{"update": {
        "status": 200, "result": "updated", "_shards": {"failed": 1},
    }}]})
    result = make_engine(client).update_by_query("idx", {"match_all": {}}, {"audit_result": 2}, requests_per_second=0)
    assert result["updated"] == 0 and len(result["failures"]) == 1


def test_new_index_creation_explicitly_preserves_source_vectors():
    client = FilteredClient()
    client.indices.exists = Mock(return_value=False)
    client.indices.create = Mock(return_value={"acknowledged": True})
    make_engine(client)._ensure_index("new-index")
    mapping = client.indices.create.call_args.kwargs["mappings"]
    assert mapping["_source"] == {"excludes": []}
    for field in ROOTS:
        assert mapping["properties"][field]["index"] is True
        assert mapping["properties"][field]["index_options"]["type"] == "hnsw"


@pytest.mark.parametrize("failure", [ClientStatusError(403), ClientStatusError(503),
                                    ConnectionError("simulated transport failure")],
                         ids=["permission", "unavailable", "transport"])
def test_get_real_failures_are_not_misreported_as_missing_or_other_index(failure):
    client = FilteredClient()
    client.get = Mock(side_effect=failure)
    with pytest.raises(type(failure)):
        make_engine(client).get("existing", index_names=["idx", "other"])
    assert client.get.call_count == 1
    assert not any(method in {"search", "update", "bulk"} for method, _ in client.calls)


def test_get_not_found_still_checks_later_index():
    client = FilteredClient()
    get_existing = client.get

    def get(**kwargs):
        if kwargs["index"] == "idx":
            raise ClientStatusError(404)
        return get_existing(**kwargs)

    client.get = Mock(side_effect=get)
    document = make_engine(client).get("existing", index_names=["idx", "other"])
    assert document["_id"] == "existing"
    assert all(field in document for field in ROOTS)
    assert client.get.call_count == 2
