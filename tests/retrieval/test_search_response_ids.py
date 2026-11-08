import kdb.entrypoints.http.retrieval.routes as retrieval_routes
import kdb.entrypoints.http.retrieval.models as retrieval_models
import kdb.entrypoints.http.retrieval.models as _http_retrieval_models
import kdb.entrypoints.http.retrieval.routes as _http_retrieval_routes
import kdb.retrieval.application.queries as _retrieval_application_queries
import importlib
import asyncio
import sys
import types


class _SearchDataInterfaceStub:
    def __init__(self, *args, **kwargs):
        pass


class _ModifyKnowledgeStub:
    def __init__(self, *args, **kwargs):
        pass


def _install_import_stubs(monkeypatch):
    search_module = types.ModuleType("kdb.retrieval.application.search_index_data_interface")
    search_module.SearchDataInterface = _SearchDataInterfaceStub
    monkeypatch.setitem(sys.modules, "kdb.retrieval.application.search_index_data_interface", search_module)

    modify_module = types.ModuleType("kdb.retrieval.modification.modify_knowledge")
    modify_module.ModifyKnowledge = _ModifyKnowledgeStub
    monkeypatch.setitem(sys.modules, "kdb.retrieval.modification.modify_knowledge", modify_module)


def test_search_response_preserves_trace_ids(monkeypatch):
    _install_import_stubs(monkeypatch)
    module = importlib.import_module("kdb.entrypoints.http.retrieval.app")

    raw_result = [
        {
            "_id": "qa-123",
            "data_type": "qa",
            "title": "How to refund?",
            "content": "Open the order and request a refund.",
            "similarity": 0.82,
            "dataset": "qa_dataset",
            "insert_time": "2026-07-01 10:00:00",
            "update_time": "2026-07-02 11:00:00",
            "ext_info": {"from_file_name": "refund.md"},
        },
        {
            "_id": "segment-456",
            "_index": "segment_index",
            "data_type": "segment",
            "content": "Return window is 30 days.",
            "similarity": 0.64,
            "insert_time": "2026-07-03 12:00:00",
            "update_time": "2026-07-04 13:00:00",
        },
    ]

    async def fake_query_remote_service(**kwargs):
        return raw_result, len(raw_result)

    monkeypatch.setattr(retrieval_routes, "query_remote_service", fake_query_remote_service)

    request = _http_retrieval_models.SearchRequest(text="refund", top_k=10)
    response = asyncio.run(_http_retrieval_routes.search(request))
    payload = response.model_dump()

    qa_item = payload["results"][0]
    assert qa_item["id"] == "qa-123"
    assert qa_item["dataset"] == "qa_dataset"
    assert qa_item["insert_time"] == "2026-07-01 10:00:00"
    assert qa_item["update_time"] == "2026-07-02 11:00:00"
    assert "_id" not in qa_item
    assert "knowledge_id" not in qa_item
    assert "doc_id" not in qa_item
    assert "qa_id" not in qa_item
    assert "source_item_id" not in qa_item

    segment_item = payload["results"][1]
    assert segment_item["id"] == "segment-456"
    assert segment_item["dataset"] == "segment_index"
    assert segment_item["insert_time"] == "2026-07-03 12:00:00"
    assert segment_item["update_time"] == "2026-07-04 13:00:00"
    assert "_id" not in segment_item
    assert "knowledge_id" not in segment_item
    assert "doc_id" not in segment_item
    assert "segment_id" not in segment_item
    assert "source_item_id" not in segment_item


def test_search_result_carries_primary_category():
    """/search 必须把知识所属类目透传出去（qa 与 segment 两个分支都要）。

    回归 2026-09-18：结果是手工列字段拼的，primary_category 一直被漏掉，
    数据其实一路都在（索引里有、search_data_by_query 也返回），只在最后序列化那步丢了。
    消费方要用 primary_category.category_path（形如「业务地区-巴西」）给每条知识标注类目，
    否则全类目检索时 LLM 分不清哪条属于哪个站点。
    """
    import kdb.entrypoints.http.retrieval.app as svc

    pc = {"cate1_name": "业务地区", "cate2_name": "巴西",
          "category_path": "业务地区-巴西", "category_ids": ["208", "209"]}
    # qa 分支：有 title
    qa = _http_retrieval_models.SearchResult(**{"id": "1", "q": "标题", "a": "正文", "score": 1.0,
                             "primary_category": pc})
    assert qa.model_dump()["primary_category"]["category_path"] == "业务地区-巴西"
    # segment 分支：无 title（q 为空字符串）
    seg = _http_retrieval_models.SearchResult(**{"id": "2", "q": "", "content": "切片正文", "score": 1.0,
                              "primary_category": pc})
    assert seg.model_dump()["primary_category"]["category_path"] == "业务地区-巴西"


def test_search_result_tolerates_missing_primary_category():
    """取不到类目时不能报错——老数据可能没有这个字段。"""
    import kdb.entrypoints.http.retrieval.app as svc
    r = _http_retrieval_models.SearchResult(**{"id": "3", "q": "x", "score": 1.0, "primary_category": None})
    assert r.model_dump()["primary_category"] is None


def test_search_top_k_default_is_safe():
    """/search 的 top_k 默认值必须在安全区（<=100）。

    回归 2026-09-19：原默认 1000 正好落在阿里云 serverless ES 容易取消分片的区间，
    线上实测同一 query 连打 8 次返回条数 628~1000 乱跳、探针缺失 4/8；
    top_k<=100 时条数恒定、零缺失。没显式传 top_k 的调用方一直在打大查询。
    """
    import kdb.entrypoints.http.retrieval.app as svc
    assert _http_retrieval_models.SearchRequest(text="x").top_k <= 100
