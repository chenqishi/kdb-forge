"""
search_multi 双路召回 + inner_hits 瘦身的回归测试。

要点：
1. recall_mode='legacy' 时构造出的查询体必须与改造前逐字节一致（不加 _source 过滤、不加 inner_hits）
2. recall_mode='dual' 时每索引发两个 body，BM25 路的 nested 必须 boost=0
3. _cal_title_similarity 有 indexes_sims 时走 inner_hits，没有时回退本地算
"""
import sys, types, json
from unittest import mock
import pytest

if "elasticsearch" not in sys.modules:
    stub = types.ModuleType("elasticsearch"); stub.Elasticsearch = object
    sys.modules["elasticsearch"] = stub

from kdb.retrieval.engines.es_search_interface import EsSearchInterfaceOri
from kdb.retrieval.engines.es_search_interface import RECALL_MODE_LEGACY
from kdb.retrieval.engines.es_search_interface import RECALL_MODE_DUAL
from kdb.retrieval.engines.es_search_interface import RECALL_ROUTE_BM25
from kdb.retrieval.engines.es_search_interface import RECALL_ROUTE_VECTOR
from kdb.retrieval.engines.es_search_interface import _INNER_HITS_NAME
from kdb.retrieval.engines.es_search_interface import RECALL_MODE_DEFAULT
from kdb.retrieval.engines.es_search_interface import _SAFE_PAGE_BATCH as esi_SAFE
import kdb.retrieval.engines.es_search_interface as _esi
esi_time = _esi.time

VEC = [0.1] * 1024
QUERY = {"query": "本土店入驻流程", "vector": {"value": VEC},
         "attribute": [{"data_type": "qa", "audit_result": [1]}]}


def _iface(mode):
    o = EsSearchInterfaceOri.__new__(EsSearchInterfaceOri)
    o.has_build_index = {"a": True, "b": True}
    o.index_name = "a"
    o.vector_fields = {"indexes_embedding": 1024}
    o.recall_mode = mode
    o.auto_update_mapping = False
    o.es = mock.MagicMock()
    o.es.msearch.return_value = {"responses": []}
    o.es.search.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
    return o


def _bodies(iface):
    """从 msearch 调用里取出各子请求的 body"""
    raw = iface.es.msearch.call_args.kwargs["body"]
    return [raw[i] for i in range(1, len(raw), 2)], [raw[i] for i in range(0, len(raw), 2)]


def test_legacy_single_index_uses_search_not_msearch():
    o = _iface(RECALL_MODE_LEGACY)
    o.search_multi(QUERY, index_names=["a"], size=20)
    o.es.search.assert_called_once()
    body = o.es.search.call_args.kwargs["body"]
    assert body["size"] == 20
    assert "_source" not in body, "legacy 不该加 _source 过滤"
    should = body["query"]["function_score"]["query"]["bool"]["should"]
    assert len(should) == 3, "legacy 应是 multi_match + synonyms + nested 三个子句融合"
    nested = [c for c in should if "nested" in c][0]["nested"]
    assert "inner_hits" not in nested, "legacy 不该加 inner_hits"
    assert "boost" not in nested


def test_dual_sends_two_bodies_per_index():
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi(QUERY, index_names=["a", "b"], size=20)
    bodies, heads = _bodies(o)
    assert [h["index"] for h in heads] == ["a", "a", "b", "b"]
    assert len(bodies) == 4
    for b in bodies:
        assert b["size"] == 10, "每路各取 size//2，总预算不变"
        assert b["_source"]["excludes"] == ["indexes.embedding", "image_indexes.embedding"]


def test_dual_bm25_route_has_no_vector_clause():
    """BM25 路不能带任何 nested 向量子句：即使 boost=0 不贡献分数，
    cosineSimilarity 仍会全量执行，等于把最贵的向量打分跑两遍
    （实测去掉后单请求 p50 1.56s→1.08s、并发4 吞吐 1.22→1.87 req/s）"""
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi(QUERY, index_names=["a"], size=20)
    bodies, _ = _bodies(o)
    bm25_should = bodies[0]["query"]["function_score"]["query"]["bool"]["should"]
    vec_should = bodies[1]["query"]["function_score"]["query"]["bool"]["should"]

    assert not [c for c in bm25_should if "nested" in c], "BM25 路不该有 nested 向量子句"
    assert any("multi_match" in c for c in bm25_should)
    assert any("match" in c and "synonyms_title" in str(c) for c in bm25_should)

    assert len(vec_should) == 1 and "nested" in vec_should[0]
    assert "boost" not in vec_should[0]["nested"], "向量路的 nested 不能被 boost 压制"
    assert vec_should[0]["nested"]["score_mode"] == "max"
    assert vec_should[0]["nested"]["inner_hits"]["name"] == _INNER_HITS_NAME


def test_dual_falls_back_when_only_vector_no_text():
    """只有向量没有文本时拆路没意义，应退回单路"""
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi({"vector": {"value": VEC}, "attribute": [{"data_type": "qa"}]},
                   index_names=["a", "b"], size=20)
    bodies, _ = _bodies(o)
    assert len(bodies) == 2, "每索引只发一个 body"
    assert bodies[0]["size"] == 20


def _hit(_id, score, indexes_texts=None, inner=None):
    """indexes_texts: _source 里的 indexes（只有 text，模拟被 _source 排除 embedding 后的样子）
       inner: [(offset, embedding)]，模拟 inner_hits 带回的项"""
    src = {"title": _id}
    if indexes_texts is not None:
        src["indexes"] = [{"text": t} for t in indexes_texts]
    h = {"_id": _id, "_score": score, "_index": "a", "_source": src}
    if inner is not None:
        h["inner_hits"] = {_INNER_HITS_NAME: {"hits": {"hits": [
            {"_score": 0.9, "_nested": {"field": "indexes", "offset": off},
             "_source": {"text": indexes_texts[off], "embedding": emb}}
            for off, emb in inner]}}}
    return h


def test_dual_merges_and_records_route():
    o = _iface(RECALL_MODE_DUAL)
    o.es.msearch.return_value = {"responses": [
        {"hits": {"total": {"value": 7}, "hits": [_hit("d1", 50.0), _hit("d2", 40.0)]}},
        {"hits": {"total": {"value": 9}, "hits": [_hit("d1", 1.7), _hit("d3", 1.6)]}},
    ]}
    docs, total = o.search_multi(QUERY, index_names=["a"], size=20)
    by_id = {d["_id"]: d for d in docs}
    assert set(by_id) == {"d1", "d2", "d3"}, "两路结果按 _id 去重合并"
    assert by_id["d1"]["score"] == 50.0, "两路都命中时保留先到的分（分数不同量纲不可比）"
    assert total == 9, "dual 下两路命中同一批数据，取最大值而不是相加"


def test_dual_duplicate_hit_merges_index_embeddings():
    """两路都命中同一条时，保留先到的那份，但要把另一份的 indexes[].embedding 合并进来。

    回归 2026-09-07：BM25 路自 bd4dae6 起不挂 nested 向量子句，其 _source 排除了
    indexes[].embedding 且无 inner_hits 可补；先到先得会让 BM25 那份占坑，
    _cal_title_similarity 的同义问法分支（要求 text in synonyms_title 且有 embedding）
    整段空转，静默退化成只用 title_embedding —— 一条同义问法与 query 逐字相同
    (cosine=1.0) 的知识最终只拿到 title 的分，排不进候选池（wayfair 线上答错事故）。
    """
    o = _iface(RECALL_MODE_DUAL)
    texts = ["标题", "同义问法A"]
    o.es.msearch.return_value = {"responses": [
        # BM25 路先返回：indexes 只有 text，没有 embedding
        {"hits": {"total": {"value": 3}, "hits": [_hit("d1", 55.0, indexes_texts=texts)]}},
        # 向量路后返回：inner_hits 带回 offset=1 的 embedding
        {"hits": {"total": {"value": 3}, "hits": [
            _hit("d1", 1.9, indexes_texts=texts, inner=[(1, [0.5] * 1024)])]}},
    ]}
    docs, _ = o.search_multi(QUERY, index_names=["a"], size=20)
    d1 = {d["_id"]: d for d in docs}["d1"]
    assert d1["score"] == 55.0, "保留先到那份的分数与排序位置"
    assert d1["indexes"][1]["embedding"] == [0.5] * 1024, "缺失的 embedding 应被另一路补齐"
    assert not d1["indexes"][0].get("embedding"), "inner_hits 没带回的项保持原样"


def test_merge_index_embeddings_does_not_overwrite_existing():
    """已有 embedding 的项不被覆盖（按 text 对齐，只补缺失项）"""
    target = {"indexes": [{"text": "A", "embedding": [1.0]}, {"text": "B"}]}
    other = {"indexes": [{"text": "A", "embedding": [9.0]}, {"text": "B", "embedding": [2.0]}]}
    EsSearchInterfaceOri._merge_index_embeddings(target, other)
    assert target["indexes"][0]["embedding"] == [1.0], "已有的不覆盖"
    assert target["indexes"][1]["embedding"] == [2.0], "缺失的补上"


def test_inner_hits_embeddings_restored_by_offset():
    """inner_hits 带回的 embedding 要按 _nested.offset 塞回 doc['indexes'] 原位，
    使 doc 结构与不做 _source 过滤时一致，下游 _cal_title_similarity 无需改动"""
    o = _iface(RECALL_MODE_DUAL)
    texts = ["标题", "同义问法A", "同义问法B", "图片文本"]
    o.es.msearch.return_value = {"responses": [
        {"hits": {"total": {"value": 1}, "hits": []}},
        {"hits": {"total": {"value": 1}, "hits": [
            _hit("d1", 1.8, texts, inner=[(1, [0.5] * 1024), (0, [0.4] * 1024)])]}},
    ]}
    docs, _ = o.search_multi(QUERY, index_names=["a"], size=20)
    idx = docs[0]["indexes"]
    assert [i["text"] for i in idx] == texts, "indexes 的 text 顺序和条数保持原样"
    assert idx[1]["embedding"] == [0.5] * 1024, "offset=1 的项拿到自己的 embedding"
    assert idx[0]["embedding"] == [0.4] * 1024, "offset=0 的项拿到自己的 embedding"
    assert "embedding" not in idx[2], "没进 inner_hits 的项没有 embedding，下游会自动跳过"
    assert "embedding" not in idx[3]


def test_inner_hits_source_includes_embedding():
    """只有向量路带 inner_hits，且必须把 embedding 一起带回来（供 offset 回填）"""
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi(QUERY, index_names=["a"], size=20)
    bodies, _ = _bodies(o)
    nested_clauses = [c for b in bodies
                      for c in b["query"]["function_score"]["query"]["bool"]["should"] if "nested" in c]
    assert len(nested_clauses) == 1, "每索引只应有向量路那一个 nested"
    ih = nested_clauses[0]["nested"]["inner_hits"]
    assert ih["_source"]["includes"] == ["indexes.text", "indexes.embedding"]


def test_legacy_multi_index_totals_are_summed():
    o = _iface(RECALL_MODE_LEGACY)
    o.es.msearch.return_value = {"responses": [
        {"hits": {"total": {"value": 7}, "hits": []}},
        {"hits": {"total": {"value": 9}, "hits": []}},
    ]}
    _, total = o.search_multi(QUERY, index_names=["a", "b"], size=20)
    assert total == 16, "legacy 多索引仍按原逻辑累加"


def test_dual_falls_back_to_legacy_without_vector():
    """没有向量时 dual 无意义，应退回单路"""
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi({"query": "abc"}, index_names=["a", "b"], size=20)
    bodies, _ = _bodies(o)
    assert len(bodies) == 2, "每索引仍只发一个 body"
    assert bodies[0]["size"] == 20


def test_default_mode_is_dual():
    assert RECALL_MODE_DEFAULT == RECALL_MODE_DUAL


def test_returned_doc_fields_identical_between_modes():
    """dual 不能给返回的文档加/减任何字段——下游拿到的键必须与 legacy 完全一致"""
    texts = ["标题", "同义问法A"]
    src = {"title": "t", "content": "c", "data_type": "qa", "synonyms_title": ["同义问法A"],
           "title_embedding": [0.1] * 4, "content_embedding": [0.2] * 4,
           "indexes": [{"text": x} for x in texts]}

    def resp(with_inner):
        h = {"_id": "d1", "_score": 1.0, "_index": "a", "_source": json.loads(json.dumps(src))}
        if with_inner:
            h["inner_hits"] = {_INNER_HITS_NAME: {"hits": {"hits": [
                {"_score": 0.9, "_nested": {"field": "indexes", "offset": 1},
                 "_source": {"text": texts[1], "embedding": [0.3] * 4}}]}}}
        return {"hits": {"total": {"value": 1}, "hits": [h]}}

    o_leg = _iface(RECALL_MODE_LEGACY)
    o_leg.es.msearch.return_value = {"responses": [resp(False), resp(False)]}
    leg, _ = o_leg.search_multi(QUERY, index_names=["a", "b"], size=20)

    o_dual = _iface(RECALL_MODE_DUAL)
    o_dual.es.msearch.return_value = {"responses": [resp(True)] * 4}
    dual, _ = o_dual.search_multi(QUERY, index_names=["a", "b"], size=20)

    assert set(leg[0]) == set(dual[0]), (
        f"字段集合不一致，dual 多出 {set(dual[0]) - set(leg[0])}，缺少 {set(leg[0]) - set(dual[0])}")
    # indexes 的条数、顺序、text 必须一致，只有 embedding 的有无不同
    assert [i["text"] for i in leg[0]["indexes"]] == [i["text"] for i in dual[0]["indexes"]]


def test_dual_does_not_leak_internal_fields():
    o = _iface(RECALL_MODE_DUAL)
    o.es.msearch.return_value = {"responses": [
        {"hits": {"total": {"value": 1}, "hits": [_hit("d1", 50.0)]}},
        {"hits": {"total": {"value": 1}, "hits": [_hit("d2", 1.7)]}},
    ]}
    docs, _ = o.search_multi(QUERY, index_names=["a"], size=20)
    for d in docs:
        assert "recall_route" not in d, "召回来源只该进日志，不能写进返回的文档"
        assert "indexes_sims" not in d
        assert "inner_hits" not in d


def test_no_query_no_vector_falls_back_to_single_route():
    """只按属性检索（无 query 文本、无向量）时，dual 必须与 legacy 生成完全相同的查询体。
    /web_search 的无 query 场景走 search_multi_by_page（未改动），这里守住 search_multi 这条。"""
    q = {"attribute": [{"quality_level": ["high"], "data_type": "qa"}]}
    bodies = {}
    for mode in (RECALL_MODE_LEGACY, RECALL_MODE_DUAL):
        o = _iface(mode)
        o.search_multi(q, index_names=["a", "b"], size=30)
        raw = o.es.msearch.call_args.kwargs["body"]
        bodies[mode] = [raw[i] for i in range(1, len(raw), 2)]
    assert len(bodies[RECALL_MODE_DUAL]) == 2, "无向量时每索引只发一个 body"
    assert json.dumps(bodies[RECALL_MODE_LEGACY], sort_keys=True) == \
           json.dumps(bodies[RECALL_MODE_DUAL], sort_keys=True), "无 query 场景两种模式必须逐字节一致"
    assert "_source" not in bodies[RECALL_MODE_DUAL][0], "没有向量就没有 inner_hits，不该做 _source 过滤"


def test_dual_both_routes_carry_identical_filters():
    """两路的 must 过滤（含自动补的 del_flag=0）必须完全一致，否则某一路会漏筛"""
    o = _iface(RECALL_MODE_DUAL)
    q = {"query": "x", "vector": {"value": VEC},
         "attribute": [{"quality_level": ["high"], "data_type": "qa"}, {"audit_result": [2]}],
         "insert_time": ["2026-01-01 00:00:00", "2026-12-31 23:59:59"]}
    o.search_multi(q, index_names=["a", "b"], size=60)
    raw = o.es.msearch.call_args.kwargs["body"]
    bodies = [raw[i] for i in range(1, len(raw), 2)]
    assert len(bodies) == 4, "2 索引 × 2 路"
    musts = {json.dumps(b["query"]["function_score"]["query"]["bool"]["must"], sort_keys=True)
             for b in bodies}
    assert len(musts) == 1, f"两路/两索引的 must 过滤不一致: {musts}"
    must = json.loads(musts.pop())
    assert {"term": {"del_flag": 0}} in must, "未指定 del_flag 时必须自动补 del_flag=0"
    assert any("range" in str(c) for c in must), "时间范围条件要落到两路"


def test_dual_del_flag_not_overridden_when_explicit():
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi({"query": "x", "vector": {"value": VEC}, "attribute": [{"del_flag": 1}]},
                   index_names=["a"], size=20)
    raw = o.es.msearch.call_args.kwargs["body"]
    for b in [raw[i] for i in range(1, len(raw), 2)]:
        must = b["query"]["function_score"]["query"]["bool"]["must"]
        assert {"term": {"del_flag": 0}} not in must, "显式指定 del_flag 时不该再补 del_flag=0"


def test_search_multi_by_page_excludes_all_vector_fields():
    """/web_search 这条路（search_multi_by_page）必须裁掉 _source 里的所有向量字段。

    这条路不做本地相似度重排、也没有 inner_hits 要补回，向量在 /web_search 出口处
    100% 会被丢弃；而单条 _source 里 97.5% 的体积是向量、size 又默认 10000，
    不裁就会把墙钟时间全耗在传输+反序列化上（实测 size=1000 12.7s -> 2.2s）。

    断言口径刻意与出口处 knowledge_database_search_es.py:629 保持一致（按 "embedding"
    子串判定），而不是逐个点名那几个字段：将来换模型加了 v2 向量、或多模态再加一路，
    只要没登记进 _PAGE_SOURCE_EXCLUDES 就会被重新带回 payload，慢速问题会悄悄回归。
    这条用例要能直接挡住那种情况。
    """
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi_by_page(QUERY, index_names=["a"], size=1000, page_num=1)
    body = o.es.search.call_args.kwargs["body"]
    excludes = body["_source"]["excludes"]

    # 模拟一条「什么向量字段都有」的文档：凡是字段名带 embedding 的，都必须被 excludes 覆盖
    doc_fields = [
        "title", "content", "indexes.text", "score",          # 正常字段，必须保留
        "indexes.embedding", "image_indexes.embedding",
        "title_embedding", "content_embedding",
    ]
    def _excluded(field):
        # 按 ES 的语义判定：精确名，或 a.b 形式下 excludes 里写了父路径，或显式通配。
        # 注意不能用裸 startswith——那样 "title_embedding_v2" 会被 "title_embedding"
        # 误判为已覆盖，正是这条用例要防的那种漏网。
        for e in excludes:
            if e.endswith("*"):
                if field.startswith(e[:-1]):
                    return True
            elif field == e or field.startswith(e + "."):
                return True
        return False

    for field in doc_fields:
        if "embedding" in field.lower():
            assert _excluded(field), (
                f"{field} 带 embedding 却没被 _source 排除——新增向量字段要同步登记到 "
                f"_PAGE_SOURCE_EXCLUDES，否则 /web_search 的 payload 会重新变大"
            )
        else:
            assert not _excluded(field), f"{field} 不是向量字段，不该被排除"


def test_search_multi_by_page_has_no_vector_clause():
    """/web_search 这条路只走 BM25，绝不能再挂 script_score 向量子句。

    索引里的 dense_vector 没开 index（ES 7.10 下是「存而不建索引」），
    nested + script_score + cosineSimilarity(match_all) 等于每次查询全量暴力重算，
    吃不到任何索引。实测 ES took：from=9000&size=1000 时 11ms vs 1569ms（143x），
    翻页越深差距越大。而这条路不做本地重排、直接用 ES 打分，拿掉向量后
    8 组真实 query 的 top1 全部不变、top10 重合 78/80。
    """
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi_by_page(QUERY, index_names=["a"], size=100, page_num=1)
    body = o.es.search.call_args.kwargs["body"]
    dumped = json.dumps(body)
    assert "cosineSimilarity" not in dumped, "向量暴力打分不能回到 /web_search 这条路"
    assert "script_score" not in dumped
    shoulds = body["query"]["function_score"]["query"]["bool"]["should"]
    s_dump = json.dumps(shoulds)
    assert "multi_match" in s_dump, "BM25 那一路必须在"
    assert "synonyms_title" in s_dump, "同义问法的 BM25 匹配必须保留"
    assert body["size"] == 100 and body["from"] == 0


def test_search_multi_by_page_still_validates_vector_dimension():
    """虽然不再用向量召回，传错维度仍要照旧被判为错误，而不是被静默放行。

    注意本方法整体 try/except 吞异常、失败返回 ([], 0)（改动前就如此，这里不动它），
    所以断言的是「返回空结果且没真的发查询」，而不是抛出 ValueError。
    """
    o = _iface(RECALL_MODE_DUAL)
    bad = dict(QUERY, vector={"value": [0.1] * 16})
    docs, total = o.search_multi_by_page(bad, index_names=["a"], size=10, page_num=1)
    assert (docs, total) == ([], 0), "维度不对要判错，不能当无事发生继续检索"
    o.es.search.assert_not_called()


def test_search_multi_keeps_vector_route_untouched():
    """守住边界：去掉 /web_search 的向量召回，绝不能波及线上 /search 走的 search_multi。"""
    o = _iface(RECALL_MODE_DUAL)
    o.search_multi(QUERY, index_names=["a"], size=20)
    bodies, _ = _bodies(o)
    dumped = json.dumps(bodies)
    assert "cosineSimilarity" in dumped, "search_multi 的向量那一路必须原样保留"


def _resp(n_hits, failed=0, total=9370):
    """构造一个 ES 响应；failed>0 模拟「分片被取消但仍返回 200」。"""
    shards = {"total": 3, "successful": 3 - failed, "failed": failed}
    if failed:
        shards["failures"] = [{"shard": 0, "reason": {"type": "task_cancelled_exception"}}]
    return {"took": 10, "_shards": shards,
            "hits": {"total": {"value": total}, "max_score": 1.0,
                     "hits": [{"_id": f"d{i}", "_score": 1.0, "_source": {"title": f"t{i}"}}
                              for i in range(n_hits)]}}


def test_shard_cancellation_is_not_silently_swallowed():
    """分片被取消时 ES 返回 200 + 空 hits + 全量 total，绝不能当成「库里没有」。

    这是最危险的失败模式：批量清洗脚本会把「查不到」误判成「不存在」而漏处理数据。
    重试仍失败必须抛错，由调用方的 except 兜底，而不是返回 ([], 0) 式的假成功。
    """
    o = _iface(RECALL_MODE_DUAL)
    o.es.search.return_value = _resp(0, failed=1)
    with mock.patch.object(esi_time, "sleep"):
        with pytest.raises(RuntimeError, match="分片查询失败"):
            o._search_once_with_retry("payoneer_olive", {"size": 100, "from": 0})
    assert o.es.search.call_count == 3, "应当重试满 3 次才放弃"


def test_shard_cancellation_recovers_on_retry():
    """分片取消是瞬时现象，重试成功就正常返回，不该把首次失败暴露给调用方。"""
    o = _iface(RECALL_MODE_DUAL)
    o.es.search.side_effect = [_resp(0, failed=1), _resp(50)]
    with mock.patch.object(esi_time, "sleep"):
        resp = o._search_once_with_retry("payoneer_olive", {"size": 50, "from": 0})
    assert len(resp["hits"]["hits"]) == 50
    assert o.es.search.call_count == 2


def test_large_size_is_split_into_safe_batches():
    """大 size 必须拆批：实测 size>=5000 时集群必败且重试无效，只能拆。"""
    o = _iface(RECALL_MODE_DUAL)
    o.es.search.side_effect = [_resp(esi_SAFE) for _ in range(4)]
    with mock.patch.object(esi_time, "sleep"):
        resp = o._search_with_shard_check("payoneer_olive", {"size": esi_SAFE * 4, "from": 0})
    assert o.es.search.call_count == 4, "应拆成 4 批"
    sizes = [c.kwargs["body"]["size"] for c in o.es.search.call_args_list]
    froms = [c.kwargs["body"]["from"] for c in o.es.search.call_args_list]
    assert sizes == [esi_SAFE] * 4
    assert froms == [0, esi_SAFE, esi_SAFE * 2, esi_SAFE * 3], "各批 from 必须顺序推进"
    assert len(resp["hits"]["hits"]) == esi_SAFE * 4, "拼接后条数要对得上"
    assert resp["hits"]["total"] == {"value": 9370}, "total 取首批的全量值，不能被拆批改写"


def test_small_size_is_not_split():
    """安全范围内的 size 不拆批——拆批会成倍放大请求数，反而更易触发分片取消。"""
    o = _iface(RECALL_MODE_DUAL)
    o.es.search.return_value = _resp(100)
    o._search_with_shard_check("payoneer_olive", {"size": 100, "from": 0})
    assert o.es.search.call_count == 1


def test_batch_stops_early_when_exhausted():
    """某批没取满说明数据到头了，必须立刻停，不能继续空转发请求。"""
    o = _iface(RECALL_MODE_DUAL)
    o.es.search.side_effect = [_resp(esi_SAFE), _resp(3)]
    with mock.patch.object(esi_time, "sleep"):
        resp = o._search_with_shard_check("payoneer_olive", {"size": esi_SAFE * 5, "from": 0})
    assert o.es.search.call_count == 2, "第二批没取满就该停"
    assert len(resp["hits"]["hits"]) == esi_SAFE + 3


def _msearch_resp(n_sub, failed_idx=()):
    """构造 msearch 响应；failed_idx 里的子请求标记为分片被取消。"""
    responses = []
    for i in range(n_sub):
        shards = {"total": 3, "successful": 3, "failed": 0}
        if i in failed_idx:
            shards = {"total": 3, "successful": 2, "failed": 1,
                      "failures": [{"shard": 0, "reason": {"type": "task_cancelled_exception"}}]}
        responses.append({"_shards": shards,
                          "hits": {"total": {"value": 5}, "hits": []}})
    return {"responses": responses}


def test_msearch_retries_on_shard_cancellation():
    """线上 /search 走 msearch：子请求分片被取消要整批重试。

    回归 2026-09-19：此前这条路只打 warning 不重试（理由是"线上 size 只有 10~40"），
    但 top_k 默认 1000 时恰好落在会抖的区间，线上实测连打 8 次条数在 628~1000 乱跳、
    探针缺失 4/8。
    """
    o = _iface(RECALL_MODE_DUAL)
    o.es.msearch.side_effect = [_msearch_resp(2, failed_idx=(0,)), _msearch_resp(2)]
    with mock.patch.object(esi_time, "sleep"):
        resp = o._msearch_with_shard_check([{"index": "a"}, {}])
    assert o.es.msearch.call_count == 2, "失败一次应重试"
    assert all(not (s.get("_shards") or {}).get("failed") for s in resp["responses"])


def test_msearch_does_not_raise_after_exhausting_retries():
    """重试用尽也不能抛错——线上问答主路宁可结果不完整也要能继续答。"""
    o = _iface(RECALL_MODE_DUAL)
    o.es.msearch.return_value = _msearch_resp(2, failed_idx=(0, 1))
    with mock.patch.object(esi_time, "sleep"):
        resp = o._msearch_with_shard_check([{"index": "a"}, {}])
    assert o.es.msearch.call_count == 3
    assert "responses" in resp, "必须返回结果而不是抛异常"


def test_single_route_search_also_retries():
    """单索引单路分支走 es.search，同样要重试。"""
    o = _iface(RECALL_MODE_DUAL)
    bad = {"_shards": {"total": 3, "successful": 2, "failed": 1},
           "hits": {"total": {"value": 0}, "hits": []}}
    good = {"_shards": {"total": 3, "successful": 3, "failed": 0},
            "hits": {"total": {"value": 7}, "hits": []}}
    o.es.search.side_effect = [bad, good]
    with mock.patch.object(esi_time, "sleep"):
        resp = o._single_search_with_retry("a", {"size": 10})
    assert o.es.search.call_count == 2
    assert resp["hits"]["total"]["value"] == 7
