"""检索链路离线差分测试：新 KnowledgeService ↔ 旧 SearchDataInterface（零 ES / 零 DashScope）。

同一输入分别驱动两套实现，断言：
① 引擎收到的请求逐字段一致（attribute 默认条件填充、size*2 扩容、索引解析、向量）；
② 每 doc similarity 逐一相等（同一 cosine 实现 + 同一 fake 向量 → 浮点完全相等）；
③ total 透传一致；④ multimodal_prefix 替换结果一致（含空前缀=删除占位符的真实语义）。

覆盖审计报告第八节建议 1 的参数矩阵与建议 2 的前缀两态。
"""

import copy

import pytest

from tests_unit.conftest import (
    FakeEmbedding,
    FakeEngine,
    build_corpus,
    make_legacy_interface,
    make_new_service,
)


def _run_both(pair, query="退货咨询", index=None, cond=None, **kw):
    legacy, svc, old_engine, new_engine = pair
    old_docs, old_total = legacy.search_data_by_query(
        query, index_names=copy.deepcopy(index), condition_dicts=copy.deepcopy(cond), **kw
    )
    new_docs, new_total = svc.search_text(
        query, index_name=copy.deepcopy(index), condition_dicts=copy.deepcopy(cond), **kw
    )
    return old_docs, old_total, new_docs, new_total, old_engine, new_engine


# ---------------- 参数矩阵（审计建议 1） ----------------
MATRIX = [
    pytest.param(dict(), id="default-conditions"),
    pytest.param(dict(cond=[{"platform": ["shopA"]}]), id="explicit-cond-audit-fill"),
    pytest.param(dict(cond=[{"audit_result": [0], "data_type": ["qa"]}]), id="cond-with-audit"),
    pytest.param(dict(use_synonyms=True), id="synonyms-on"),
    pytest.param(dict(search_type="doc"), id="search-type-doc"),
    pytest.param(dict(data_type="image"), id="data-type-image"),
    pytest.param(dict(data_type="text_image", use_synonyms=True, search_type="doc"), id="mixed"),
    pytest.param(dict(index="idxa"), id="single-index"),
    pytest.param(dict(index="idxA,idxB"), id="multi-index-comma"),
    pytest.param(dict(size=3), id="size-3"),
]


@pytest.mark.parametrize("case", MATRIX)
def test_search_text_matches_legacy(pair, case):
    case = dict(case)
    index = case.pop("index", None)
    cond = case.pop("cond", None)
    old_docs, old_total, new_docs, new_total, old_engine, new_engine = _run_both(
        pair, index=index, cond=cond, **case
    )

    # ① 引擎请求完全一致（含解析后的索引、attribute、size*2、page_num、向量）
    assert old_engine.calls == new_engine.calls
    assert len(new_engine.calls_of("search_multi")) == 1

    # ② 返回加工结果一致
    assert old_total == new_total
    assert [d["_id"] for d in old_docs] == [d["_id"] for d in new_docs]
    for od, nd in zip(old_docs, new_docs):
        assert od["similarity"] == nd["similarity"], od["_id"]
        assert od.get("content") == nd.get("content")  # 前缀替换一致
        assert od == nd


def test_search_default_condition_contract(pair):
    """锁定默认条件组与 size*2 扩容契约（不依赖旧实现也能看懂的显式断言）。"""
    _, _, _, new_engine = pair[0], pair[1], pair[2], pair[3]
    pair[1].search_text("q", size=4)
    call = new_engine.calls_of("search_multi")[0]
    assert call["size"] == 8  # size*2
    assert call["query"]["attribute"] == [
        {"quality_level": ["high"], "data_type": ["qa"], "audit_result": [1, 2, -1]},
        {"audit_result": [1, 2], "data_type": ["qa"]},
    ]
    assert call["index"] == "test_case"  # 默认索引兜底 + 小写


def test_search_condition_inplace_mutation_side_effect(pair):
    """与旧一致的副作用契约：显式 condition_dicts 会被**原地**补 audit_result。"""
    legacy, svc = pair[0], pair[1]
    old_cond = [{"platform": ["p"]}]
    new_cond = [{"platform": ["p"]}]
    legacy.search_data_by_query("q", condition_dicts=old_cond)
    svc.search_text("q", condition_dicts=new_cond)
    assert old_cond == new_cond == [{"platform": ["p"], "audit_result": [1, 2, -1]}]


def test_search_index_list_is_safe_superset(pair):
    """新实现接受 List[str]（旧传 list 会 AttributeError）——安全超集契约。"""
    legacy, svc, old_engine, new_engine = pair
    with pytest.raises(AttributeError):
        legacy.search_data_by_query("q", index_names=["idxa", "idxb"])
    docs, total = svc.search_text("q", index_name=["idxa", "idxb"])
    assert new_engine.calls_of("search_multi")[0]["index"] == "idxa,idxb"
    assert total == 7


def test_legacy_alias_signature(pair):
    """旧关键字参数名 index_names 经 alias 可用（迁移不需要改调用方代码）。"""
    _, svc, _, new_engine = pair
    svc.search_data_by_query("q", index_names="idxa,idxb", size=2)
    call = new_engine.calls_of("search_multi")[0]
    assert call["index"] == "idxa,idxb" and call["size"] == 4


@pytest.mark.parametrize("prefix", ["https://file.example.com/", ""])
def test_multimodal_prefix_two_states(prefix):
    """前缀两态契约（审计建议 2）：非空=替换；**空串=删除占位符**（不是保留），新旧一致。"""
    emb = FakeEmbedding()
    corpus = build_corpus(FakeEmbedding())
    legacy = make_legacy_interface(FakeEngine(docs=corpus), emb, multimodal_prefix=prefix)
    svc = make_new_service(FakeEngine(docs=copy.deepcopy(corpus)), emb, multimodal_prefix=prefix)
    old_docs, _ = legacy.search_data_by_query("运费")
    new_docs, _ = svc.search_text("运费")
    old_d2 = next(d for d in old_docs if d["_id"] == "d2")
    new_d2 = next(d for d in new_docs if d["_id"] == "d2")
    assert old_d2["content"] == new_d2["content"] == f"运费说明 {prefix}img/a.png"


def test_search_embedding_failure_raises_on_both(pair):
    """检索路径错误契约：embedding 异常两边都**上抛**（与写路径不同）。"""
    legacy, svc = pair[0], pair[1]
    legacy.embedding_tools.fail = True  # 同一实例，两边共享
    with pytest.raises(Exception, match="fake embedding down"):
        legacy.search_data_by_query("q")
    with pytest.raises(Exception, match="fake embedding down"):
        svc.search_text("q")


# ---------------- 多 query（search_data_by_multi_query ↔ search_text_multi） ----------------
def _run_both_multi(pair, query_list, index=None, cond=None, **kw):
    legacy, svc, old_engine, new_engine = pair
    old = legacy.search_data_by_multi_query(
        list(query_list), index_names=copy.deepcopy(index), condition_dicts=copy.deepcopy(cond), **kw
    )
    new = svc.search_text_multi(
        list(query_list), index_name=copy.deepcopy(index), condition_dicts=copy.deepcopy(cond), **kw
    )
    return old, new, old_engine, new_engine


@pytest.mark.parametrize("case", [
    pytest.param(dict(query_list=["退货", "发票"]), id="two-queries"),
    pytest.param(dict(query_list=["退货"]), id="one-query"),
    pytest.param(dict(query_list=["退货", "发票"], cond=[{"platform": ["p"]}]), id="cond-fill-1-minus1"),
    pytest.param(dict(query_list=["退货", "发票"], index="idxa,idxb"), id="multi-index"),
    pytest.param(dict(query_list=["退货", "发票"], use_synonyms=True, data_type="image"), id="syn-image"),
])
def test_multi_query_matches_legacy(pair, case):
    case = dict(case)
    old, new, old_engine, new_engine = _run_both_multi(
        pair, case.pop("query_list"), index=case.pop("index", None), cond=case.pop("cond", None), **case
    )
    assert old_engine.calls == new_engine.calls
    assert old[1] == new[1]
    assert [d["_id"] for d in old[0]] == [d["_id"] for d in new[0]]
    for od, nd in zip(old[0], new[0]):
        assert od == nd


def test_multi_query_default_condition_contract(pair):
    """多 query 的默认条件与单 query **不同**：audit_result=[1]，缺省补 [1,-1]。"""
    _, svc, _, new_engine = pair
    svc.search_text_multi(["q1"], size=5)
    call = new_engine.calls_of("search_multi")[0]
    assert call["size"] == 10
    assert call["query"]["attribute"] == [
        {"quality_level": ["high"], "data_type": ["qa"], "audit_result": [1, -1]},
        {"audit_result": [1], "data_type": ["qa"]},
    ]
    # 多 query 主路径**不做**前缀替换（旧实现如此；回退路径经 search_text 才替换）
    assert any("[multimodal_prefix]" in (d.get("content") or "") for d in svc.search_text_multi(["q1"])[0])


def test_multi_query_empty_list(pair):
    old, new, old_engine, new_engine = _run_both_multi(pair, [])
    assert old == new == ([], 0)
    assert old_engine.calls == new_engine.calls == []


def test_multi_query_mixed_empty_misalignment_contract(pair):
    """锁定旧实现已知怪癖：query_list 混空串时向量下标错位 → 相似度记 0。新旧一致复刻。"""
    old, new, old_engine, new_engine = _run_both_multi(pair, ["", "退货"])
    assert old_engine.calls == new_engine.calls
    assert [d["similarity"] for d in old[0]] == [d["similarity"] for d in new[0]]
    # 下标 1 >= len(query_embeddings)==1 → 取不到向量 → 全部 doc 相似度为 0
    assert all(d["similarity"] == 0 for d in new[0])


def test_multi_query_threading_fallback_no_index(pair):
    """主路径异常 → 多线程回退：index=None 时新旧结果一致（去重合并、按相似度排序、截断）。

    注意：多个 query 时新旧实现同样存在**线程完成序竞态**（去重保留先完成 query 的
    similarity），旧 vs 旧也不可复现，故逐字节对比只用单 query；多 query 只比集合/截断。
    """
    legacy, svc, old_engine, new_engine = pair
    old_engine.raise_on_multi_list_query = True
    new_engine.raise_on_multi_list_query = True
    # 单 query：确定性，逐字节相等
    old = legacy.search_data_by_multi_query(["退货"], size=2)
    new = svc.search_text_multi(["退货"], size=2)
    assert old[1] == new[1]
    assert len(new[0]) == 2  # 回退路径按相似度排序后截断 size
    assert [d["_id"] for d in old[0]] == [d["_id"] for d in new[0]]
    for od, nd in zip(old[0], new[0]):
        assert od == nd
    sims = [d["similarity"] for d in new[0]]
    assert sims == sorted(sims, reverse=True)
    # 多 query：竞态下只断言命中集合与 total 一致
    old2 = legacy.search_data_by_multi_query(["退货", "发票"], size=10)
    new2 = svc.search_text_multi(["退货", "发票"], size=10)
    assert old2[1] == new2[1]
    assert {d["_id"] for d in old2[0]} == {d["_id"] for d in new2[0]}


def test_multi_query_threading_fallback_with_index_fixed():
    """有意修复契约：显式索引时旧回退因 `list.split` AttributeError 恒返回空；新回退返回真实结果。

    差异记录：docs/CRUD_Legacy_Difference_Issues.md（多 query 回退修复）。
    """
    emb = FakeEmbedding()
    corpus = build_corpus(FakeEmbedding())
    old_engine = FakeEngine(docs=corpus, total=7)
    new_engine = FakeEngine(docs=copy.deepcopy(corpus), total=7)
    old_engine.raise_on_multi_list_query = True
    new_engine.raise_on_multi_list_query = True
    legacy = make_legacy_interface(old_engine, emb)
    svc = make_new_service(new_engine, emb)

    old = legacy.search_data_by_multi_query(["退货"], index_names="idxa,idxb", size=5)
    new = svc.search_text_multi(["退货"], index_name="idxa,idxb", size=5)
    assert old == ([], 0)  # 旧：回退内部逐 query AttributeError 被吞 → 恒空
    assert new[1] == 7
    assert {d["_id"] for d in new[0]} == {"d1", "d2", "d3"}  # 新：回退返回真实结果


# ---------------- web_search_data ↔ web_search ----------------
def _run_both_web(pair, query, **kw):
    legacy, svc, old_engine, new_engine = pair
    old = legacy.web_search_data(query, **copy.deepcopy(kw))
    kw_new = dict(kw)
    if "index_names" in kw_new:
        kw_new["index_name"] = kw_new.pop("index_names")
    new = svc.web_search(query, **copy.deepcopy(kw_new))
    return old, new, old_engine, new_engine


@pytest.mark.parametrize("case", [
    pytest.param(dict(query="退货"), id="basic"),
    pytest.param(dict(query=""), id="empty-query-no-embed"),
    pytest.param(dict(query="退货", index_names="idxa,idxb", page_size=2, page_num=3), id="paging"),
    pytest.param(dict(query="退货", score_threshold=0.35), id="score-threshold"),
    pytest.param(dict(query="退货", condition_dicts=[{"platform": ["p"]}]), id="no-default-cond"),
])
def test_web_search_matches_legacy(pair, case):
    case = dict(case)
    old, new, old_engine, new_engine = _run_both_web(pair, case.pop("query"), **case)
    assert old_engine.calls == new_engine.calls
    assert old[1] == new[1]
    for od, nd in zip(old[0], new[0]):
        assert od == nd


def test_web_search_contract_details(pair):
    """锁定 web_search 独有契约：page_size 缺省 10000、score/5.0 归一、空 query 不 embed。"""
    legacy, svc, old_engine, new_engine = pair
    docs, total = svc.web_search("")
    call = new_engine.calls_of("search_multi_by_page")[0]
    assert call["size"] == 10000 and call["page_num"] == 1 and call["score_threshold"] is None
    assert call["query"] == {"attribute": []}  # 空 query：无 query/vector 键，无默认条件
    assert svc._embedding.calls == []  # 未调用 embedding
    # score 归一化：min(score/5.0, 1.0)
    by_id = {d["_id"]: d for d in docs}
    assert by_id["d1"]["score"] == 3.2 / 5.0
    assert by_id["d2"]["score"] == 2.1 / 5.0
    # 前缀替换发生在 web_search 返回前
    assert by_id["d2"]["content"] == "运费说明 https://file.example.com/img/a.png"


def test_web_search_category_names_mapping(pair):
    """category_names → category_ids：映射命中的转 id、未命中的丢弃、与显式 ids 合并、原键移除。"""
    legacy, svc, old_engine, new_engine = pair
    chain = [
        {"category_name": "家电", "category_id": "c1", "level": 1},
        {"category_name": "冰箱", "category_id": "c2", "level": 2},
    ]
    mapping = {"idxa": {"name_map_dict": {"家电-冰箱": chain}, "id_map_dict": {}}}
    legacy.all_client_category_dict = copy.deepcopy(mapping)
    svc._category.all_client_category_dict = copy.deepcopy(mapping)

    # client 缺省取第一个索引名（split 后原样，与旧一致）：'idxa' 命中 mapping
    cond = [{"category_names": ["家电-冰箱", "不存在的类目"], "category_ids": ["c9"], "platform": "p"}]
    old, new, *_ = _run_both_web(pair, "退货", index_names="idxa,idxb", condition_dicts=cond)
    assert old_engine.calls == new_engine.calls
    sent = new_engine.calls_of("search_multi_by_page")[0]["query"]["attribute"]
    assert sent == [{"platform": "p", "category_ids": ["c2", "c9"]}]

    # 显式 client + 单值（非 list）category_names 也接受
    old_engine.calls.clear(); new_engine.calls.clear()
    cond2 = [{"category_names": "家电-冰箱"}]
    old2, new2, *_ = _run_both_web(pair, "退货", client="idxa", condition_dicts=cond2)
    assert old_engine.calls == new_engine.calls
    assert new_engine.calls_of("search_multi_by_page")[0]["query"]["attribute"] == [
        {"category_ids": ["c2"]}
    ]
