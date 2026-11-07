"""写入链路离线差分测试：新 insert_data/find_duplicates/batch ↔ 旧实现（零 ES / 零 DashScope）。

覆盖审计报告 P1-1（去重）、P2-1/2/3（audit_result 矫正、insert_time、错误契约）、
P3-1/2/3（from_type、keywords 异常、multimodal 边界）。时间用 monkeypatch 冻结，
两边产出的引擎写入 payload 逐字节可比。

**有意与旧不同并在此锁定契约的差异**（记录于 docs/CRUD_Legacy_Difference_Issues.md）：
- 带 `_id` 缺 `insert_time`：旧整条失败（KeyError→'数据处理失败'），新成功且不带该字段。
- 旧 insert_data 往调用方 dict 塞 `_id=None` 的副作用不复刻。
"""

import copy
from datetime import datetime

import pytest

from tests_unit.conftest import (
    FakeEmbedding,
    FakeEngine,
    make_legacy_interface,
    make_new_service,
)

FROZEN = datetime(2026, 1, 2, 3, 4, 5)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN


@pytest.fixture(autouse=True)
def frozen_time(monkeypatch):
    import knowledge_interface_tools.search_index_data_interface as old_mod

    import kdb.crud.service as new_mod

    monkeypatch.setattr(old_mod, "datetime", _FrozenDatetime)
    monkeypatch.setattr(new_mod, "datetime", _FrozenDatetime)


def _pair(check_duplicate=False, search_docs=None):
    emb = FakeEmbedding()
    old_engine = FakeEngine(search_docs=copy.deepcopy(search_docs) if search_docs else [])
    new_engine = FakeEngine(search_docs=copy.deepcopy(search_docs) if search_docs else [])
    legacy = make_legacy_interface(old_engine, emb, check_duplicate=check_duplicate)
    svc = make_new_service(new_engine, emb, check_duplicate=check_duplicate)
    return legacy, svc, old_engine, new_engine


def _insert_both(doc, check_duplicate=False, search_docs=None, **kw):
    legacy, svc, old_engine, new_engine = _pair(check_duplicate=check_duplicate,
                                                search_docs=search_docs)
    old_res = legacy.insert_data(copy.deepcopy(doc), **copy.deepcopy(kw))
    new_res = svc.insert_data(copy.deepcopy(doc), **copy.deepcopy(kw))
    return old_res, new_res, old_engine, new_engine


def _payloads(old_engine, new_engine):
    old_ins = old_engine.calls_of("insert")
    new_ins = new_engine.calls_of("insert")
    assert len(old_ins) == len(new_ins)
    return old_ins, new_ins


# ---------------- 基础 prepare/insert 对齐 ----------------
@pytest.mark.parametrize("doc", [
    pytest.param({"title": "如何退货", "content": "联系客服", "data_type": "qa",
                  "platform": "shopA", "trace_id": "t1", "custom": "x"},
                 id="minimal-qa-with-ext-fields"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa", "is_audit": 1},
                 id="is-audit-migration"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa", "audit_result": 5},
                 id="invalid-audit-new-doc"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa", "audit_result": 0},
                 id="audit-zero-untouched-truthiness"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa", "quality_level": "super"},
                 id="invalid-quality-new-doc"),
    pytest.param({"title": "T", "content": "C", "data_type": "segment",
                  "synonyms_title": ["s"]}, id="segment-drops-title"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa",
                  "synonyms_title": "not-a-list"}, id="synonyms-not-list"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa",
                  "synonyms_title": ["同义A", 123]}, id="synonyms-skip-non-str"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa", "from_type": 123},
                 id="from-type-int-new-doc"),
    pytest.param({"title": "图文", "data_type": "qa",
                  "image_indexes": [{"text": "图片描述"}]}, id="image-indexes-redundant-text"),
    pytest.param({"title": "T", "content": "C", "data_type": "qa",
                  "category_infos": [{"category_id": 88, "score": 0.9}]},
                 id="category-id-to-str"),
    pytest.param({"_id": "fixed-id", "title": "T", "content": "C", "data_type": "qa",
                  "insert_time": "2025-01-01 00:00:00"}, id="upsert-with-id-defaults-skipped"),
    pytest.param({"_id": "fixed-id", "title": "T", "content": "C", "data_type": "qa",
                  "insert_time": 123456}, id="non-str-insert-time-reset"),
    pytest.param({"_id": "fixed-id", "title": "T", "content": "C", "data_type": "qa",
                  "insert_time": "2025-01-01 00:00:00", "audit_result": 7},
                 id="P2-1-invalid-audit-with-id-now-corrected"),
    pytest.param({"_id": "fixed-id", "title": "T", "content": "C", "data_type": "qa",
                  "insert_time": "2025-01-01 00:00:00", "from_type": 456},
                 id="P3-1-from-type-int-with-id-converted"),
    pytest.param({"title": "多模态", "data_type": "qa", "multimodal_contents": [
        {"type": "text", "content": "头部"},
        {"type": "image", "path": "img/a.png"},
        {"type": "file", "url": "http://u/x"},
        {"type": "audio"},                      # 无 path/url → 跳过
    ]}, id="multimodal-join"),
    pytest.param({"title": "多模态怪癖", "data_type": "qa", "multimodal_contents": [
        {"type": "text", "content": "头部"},
        {"type": "text"},                       # 缺 content → 旧拼出字面 "\nNone"
    ]}, id="multimodal-none-quirk"),
])
def test_insert_payload_matches_legacy(doc):
    old_res, new_res, old_engine, new_engine = _insert_both(doc)
    assert old_res == new_res == (True, "")
    old_ins, new_ins = _payloads(old_engine, new_engine)
    assert old_ins[0] == new_ins[0]  # payload + 解析后索引 + refresh_imm 全部一致


def test_insert_index_name_and_dataset_contract():
    """index_name 传递契约：insert_data 不兜底 dataset（与旧一致）；显式传时 dataset=index。"""
    doc = {"title": "T", "content": "C", "data_type": "qa"}
    old_res, new_res, old_engine, new_engine = _insert_both(doc)
    o, n = _payloads(old_engine, new_engine)
    assert "dataset" not in n[0]["data"] and "dataset" not in o[0]["data"]

    old_res, new_res, old_engine, new_engine = _insert_both(doc, index_name="idx_x")
    o, n = _payloads(old_engine, new_engine)
    assert o[0] == n[0]
    assert n[0]["data"]["dataset"] == "idx_x" and n[0]["index"] == "idx_x"


def test_insert_time_missing_with_id_divergence_contract():
    """P2-2 有意修复契约：带 `_id` 缺 insert_time——旧整条失败，新成功且不带 insert_time。"""
    doc = {"_id": "fixed-id", "title": "T", "content": "C", "data_type": "qa"}
    old_res, new_res, old_engine, new_engine = _insert_both(doc)
    assert old_res == (False, "数据处理失败")   # 旧：KeyError 被兜成处理失败
    assert new_res == (True, "")               # 新：修复为可正常 upsert
    assert old_engine.calls_of("insert") == []
    payload = new_engine.calls_of("insert")[0]["data"]
    assert "insert_time" not in payload
    assert payload["update_time"] == FROZEN.strftime("%Y-%m-%d %H:%M:%S")


def test_insert_no_id_none_side_effect_divergence_contract():
    """有意差异契约：旧往调用方 dict 塞 `_id=None`（破坏同 dict 二次插入）；新不修改入参。"""
    legacy, svc, *_ = _pair()
    old_doc = {"title": "T", "content": "C", "data_type": "qa"}
    new_doc = {"title": "T", "content": "C", "data_type": "qa"}
    legacy.insert_data(old_doc)
    svc.insert_data(new_doc)
    assert "_id" in old_doc and old_doc["_id"] is None  # 旧副作用
    assert new_doc == {"title": "T", "content": "C", "data_type": "qa"}  # 新：入参不动


def test_keywords_runtime_error_fails_insert_on_both(monkeypatch):
    """P3-2 对齐：jieba 运行期异常 → 两边 insert_data 都 (False,'数据处理失败')。"""
    import knowledge_interface_tools.search_index_data_interface as old_mod

    import kdb.crud.service as new_mod

    def boom(*a, **k):
        raise RuntimeError("jieba down")

    monkeypatch.setattr(old_mod, "gen_keyword_by_title_content", boom)
    monkeypatch.setattr(new_mod, "legacy_gen_keyword_by_title_content", boom)
    doc = {"title": "T", "content": "C", "data_type": "qa"}
    old_res, new_res, old_engine, new_engine = _insert_both(doc)
    assert old_res == new_res == (False, "数据处理失败")
    assert old_engine.calls_of("insert") == new_engine.calls_of("insert") == []


def test_embedding_failure_contract():
    """P2-3 错误契约：insert_data 兜成 (False,'数据处理失败')（旧契约）；insert_text 上抛（新 API）。"""
    legacy, svc, old_engine, new_engine = _pair()
    legacy.embedding_tools.fail = True  # 同一实例
    doc = {"title": "T", "content": "C", "data_type": "qa"}
    assert legacy.insert_data(dict(doc)) == (False, "数据处理失败")
    assert svc.insert_data(dict(doc)) == (False, "数据处理失败")
    with pytest.raises(Exception, match="fake embedding down"):
        svc.insert_text(dict(doc))


def test_engine_insert_failure_returns_false_empty_msg():
    """引擎写入失败：两边都返回 (False, '')——旧文案契约（不是 'insert failed'）。"""
    legacy, svc, old_engine, new_engine = _pair()
    old_engine.insert_ok = False
    new_engine.insert_ok = False
    doc = {"title": "T", "content": "C", "data_type": "qa"}
    assert legacy.insert_data(dict(doc)) == svc.insert_data(dict(doc)) == (False, "")


# ---------------- 去重（P1-1） ----------------
def _dup_candidate(emb, title="如何退货", content="联系客服", _id=None, platform="shopA"):
    """与待插文档同 embedding 的既有候选（相似度=1 → 必判重复）。"""
    e = lambda t: emb.text2embedding(t).tolist()  # noqa: E731
    return {
        "_id": _id or "existing-dup", "title": title, "content": content,
        "data_type": "qa", "platform": platform,
        "title_embedding": e(title), "content_embedding": e(content),
    }


def test_insert_duplicate_rejected_on_both():
    """默认查重：候选相似 → 两边 (False,'数据重复')，且 find_duplicates 检索请求一致。"""
    emb_probe = FakeEmbedding()
    doc = {"title": "如何退货", "content": "联系客服", "data_type": "qa", "platform": "shopA"}
    cand = _dup_candidate(emb_probe)
    old_res, new_res, old_engine, new_engine = _insert_both(
        doc, check_duplicate=True, search_docs=[cand]
    )
    assert old_res == new_res == (False, "数据重复")
    assert old_engine.calls == new_engine.calls  # 含 find_duplicates 的 search 请求
    assert old_engine.calls_of("insert") == []
    # find_duplicates 的检索契约：title+content 文本、首 index 向量、data_type/platform 过滤
    q = new_engine.calls_of("search")[0]["query"]
    assert q["query"] == "如何退货 联系客服"
    assert q["attribute"] == {"data_type": "qa", "platform": "shopA"}
    assert "vector" in q


def test_insert_duplicate_self_id_excluded():
    """exclude_self=True（insert_data 内部）：候选 _id 与新文档相同 → 不算重复，正常插入。"""
    emb_probe = FakeEmbedding()
    doc = {"title": "如何退货", "content": "联系客服", "data_type": "qa", "platform": "shopA"}
    # 先算出新文档将得到的 _id（title_content_data_type 的 md5），做成"自身"候选
    from kdb.crud.ids import gen_data_id
    self_id = gen_data_id({"title": "如何退货", "content": "联系客服", "data_type": "qa"})
    cand = _dup_candidate(emb_probe, _id=self_id)
    old_res, new_res, old_engine, new_engine = _insert_both(
        doc, check_duplicate=True, search_docs=[cand]
    )
    assert old_res == new_res == (True, "")
    assert old_engine.calls_of("insert")[0] == new_engine.calls_of("insert")[0]


def test_insert_duplicate_is_update_data_soft_deletes_then_inserts():
    """is_update_data=True：软删（update_value del_flag=1/del_reason=cover_by_new）后继续插入。"""
    emb_probe = FakeEmbedding()
    doc = {"title": "如何退货", "content": "联系客服", "data_type": "qa", "platform": "shopA"}
    cand = _dup_candidate(emb_probe)
    old_res, new_res, old_engine, new_engine = _insert_both(
        doc, check_duplicate=True, search_docs=[cand], is_update_data=True, index_name="idx_x"
    )
    assert old_res == new_res == (True, "")
    assert old_engine.calls == new_engine.calls
    uv = new_engine.calls_of("update_value")[0]
    assert uv["update_value_dict"]["del_flag"] == 1
    assert uv["update_value_dict"]["del_reason"].startswith("cover_by_new ")
    assert uv["conditions"] == [{"_id": ["existing-dup"]}]
    assert len(new_engine.calls_of("insert")) == 1


def test_insert_not_duplicate_below_threshold():
    """候选不相似（不同向量 / max_sim < basic_threshold）→ 正常插入，两边一致。"""
    emb_probe = FakeEmbedding()
    doc = {"title": "如何退货", "content": "联系客服", "data_type": "qa", "platform": "shopA"}
    cand = _dup_candidate(emb_probe, title="发票抬头", content="开票流程说明", _id="other")
    old_res, new_res, old_engine, new_engine = _insert_both(
        doc, check_duplicate=True, search_docs=[cand]
    )
    assert old_res == new_res == (True, "")
    assert old_engine.calls == new_engine.calls


def test_find_duplicates_direct_matches_legacy():
    """find_duplicates 直接调用：返回的重复列表一致；exclude_self=False 时自身算重复。"""
    emb = FakeEmbedding()
    cand_src = FakeEmbedding()
    doc = {"title": "如何退货", "content": "联系客服", "data_type": "qa", "platform": "shopA"}
    from kdb.crud.ids import gen_data_id
    self_id = gen_data_id({"title": "如何退货", "content": "联系客服", "data_type": "qa"})
    cands = [_dup_candidate(cand_src, _id=self_id), _dup_candidate(cand_src, _id="another-dup")]
    old_engine = FakeEngine(search_docs=copy.deepcopy(cands))
    new_engine = FakeEngine(search_docs=copy.deepcopy(cands))
    legacy = make_legacy_interface(old_engine, emb)
    svc = make_new_service(new_engine, emb)

    old_dups = legacy.find_duplicates(copy.deepcopy(doc), is_need_llm=False)
    new_dups = svc.find_duplicates(copy.deepcopy(doc), is_need_llm=False)
    assert [d["_id"] for d in old_dups] == [d["_id"] for d in new_dups] == [self_id, "another-dup"]

    old_dups2 = legacy.find_duplicates(copy.deepcopy(doc), is_need_llm=False, exclude_self=True)
    new_dups2 = svc.find_duplicates(copy.deepcopy(doc), is_need_llm=False, exclude_self=True)
    assert [d["_id"] for d in old_dups2] == [d["_id"] for d in new_dups2] == ["another-dup"]


def test_batch_insert_data_matches_legacy():
    docs = [
        {"title": "A", "content": "a", "data_type": "qa"},
        {"title": "B", "content": "b", "data_type": "qa"},
    ]
    legacy, svc, old_engine, new_engine = _pair()
    old_res = legacy.batch_insert_data(copy.deepcopy(docs), check_duplicate=False)
    new_res = svc.batch_insert_data(copy.deepcopy(docs), check_duplicate=False)
    assert old_res == new_res == [(True, ""), (True, "")]
    assert old_engine.calls == new_engine.calls


# ---------------- 旧透传接口 alias ----------------
def test_legacy_passthrough_aliases_match():
    """update_data/delete_data/get_data_by_id/search_data/update_data_value/get_unique_values 透传一致。"""
    legacy, svc, old_engine, new_engine = _pair()
    legacy.update_data("id1", {"title": "x"})
    svc.update_data("id1", {"title": "x"})
    legacy.delete_data("id2", index_names="idx_y", refresh=True)
    svc.delete_data("id2", index_names="idx_y", refresh=True)
    legacy.get_data_by_id("id3")
    svc.get_data_by_id("id3")
    legacy.search_data({"query": "q"}, size=7, index_names="idx_z")
    svc.search_data({"query": "q"}, size=7, index_names="idx_z")
    legacy.update_data_value("idx_w", {"del_flag": 1}, [{"platform": "p"}])
    svc.update_data_value("idx_w", {"del_flag": 1}, [{"platform": "p"}])
    legacy.get_unique_values("idx_v", "platform", size=5, include_doc_count=True)
    svc.get_unique_values("idx_v", "platform", size=5, include_doc_count=True)
    assert old_engine.calls == new_engine.calls


# ---------------- Repository 新包装（引擎能力委托） ----------------
def test_repository_engine_capability_wrappers():
    """scroll_search/search_after/get_field_statistics/update_index_map/insert_with_vectors/
    search_by_vector 与旧引擎直调入参一致（索引缺省解析为默认索引）。"""
    from kdb.crud.repository import KnowledgeRepository

    old_engine = FakeEngine()
    new_engine = FakeEngine()
    repo = KnowledgeRepository(engine=new_engine)

    q = {"attribute": {"data_type": "qa"}}
    list(old_engine.scroll_search(q, batch_size=500, scroll_timeout="10m", index_names=None))
    list(repo.scroll_search(q, batch_size=500, scroll_timeout="10m"))
    list(old_engine.search_after(q, batch_size=200, sort_field="_id", index_names="idx_a"))
    list(repo.search_after(q, batch_size=200, sort_field="_id", index_name="idx_a"))
    old_engine.get_field_statistics("test_case", "platform", extra_query=None)
    repo.get_field_statistics("platform")
    old_engine.update_index_map("test_case", {"properties": {"new_f": {"type": "keyword"}}})
    repo.update_index_map({"properties": {"new_f": {"type": "keyword"}}})
    old_engine.insert_with_vectors({"_id": "v1", "title": "t"}, {"title_embedding": [0.1] * 8})
    repo.insert_with_vectors({"_id": "v1", "title": "t"}, {"title_embedding": [0.1] * 8})
    old_engine.search_by_vector([0.1] * 8, "title_embedding", size=3, min_score=0.2,
                                return_score=True, extra_query=None, index_names=None)
    repo.search_by_vector([0.1] * 8, "title_embedding", size=3, min_score=0.2, return_score=True)
    assert old_engine.calls == new_engine.calls
