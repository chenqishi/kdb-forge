# -*- coding: utf-8 -*-
"""按来源文件名删除知识的回归测试。

守住三条硬约束（依据 docs/按文件名删除知识服务_方案.md 与线上实测）：
1. 只作用于非对话来源，且必须用白名单而非黑名单
2. match_mode 严格二选一，exact 不转模糊、fuzzy 不退回精确
3. 删除必须经 preview 的 confirm_token + expected_count 双校验
"""
import json
import sys
import types
from unittest import mock

import pytest

if "elasticsearch" not in sys.modules:  # 与其它用例一致，避免真的装 es 依赖
    stub = types.ModuleType("elasticsearch")
    stub.Elasticsearch = object
    sys.modules["elasticsearch"] = stub

from kdb.retrieval.application.search_index_data_interface import SearchDataInterface

SCOPE = ["document", "html", "manual"]


def _iface():
    """造一个不连 ES 的 SearchDataInterface，engine 全 mock。"""
    o = SearchDataInterface.__new__(SearchDataInterface)
    o.engine = mock.MagicMock()
    o.engine.count_by_query.return_value = 0
    o.engine.agg_terms.return_value = []
    o.engine.sample_by_query.return_value = []
    return o


def _musts(query):
    return query["bool"]["must"]


# ---------------- 来源范围 ----------------

def test_scope_uses_whitelist_not_blacklist():
    """必须用 terms 白名单圈定非对话来源。

    存量里 auto_learning 还有中文旧写法「自动学习」（实测 payoneer_olive 334 条），
    用 must_not=auto_learning 的黑名单会让这批漏网被删。
    """
    o = _iface()
    q = o._build_file_query(["a.pdf"])
    terms = [m["terms"]["from_type_norm"] for m in _musts(q) if "terms" in m
             and "from_type_norm" in m["terms"]]
    assert terms and sorted(terms[0]) == sorted(SCOPE)
    assert "must_not" not in q["bool"], "不能用黑名单，中文旧写法会漏网"
    assert json.dumps(q, ensure_ascii=False).count("auto_learning") == 0


def test_every_query_filters_deleted_and_scope():
    o = _iface()
    for q in (o._build_file_query(["a.pdf"]),
              {"bool": {"must": o._scope_filters()}}):
        dumped = json.dumps(_musts(q), ensure_ascii=False)
        assert '"del_flag": 0' in dumped.replace(" ", "").replace('"del_flag":0', '"del_flag": 0')
        assert "from_type_norm" in dumped


def test_list_file_names_applies_scope_and_keyword():
    o = _iface()
    o.engine.agg_terms.return_value = [
        {"key": "a.pdf", "doc_count": 3, "sub": {"by_type": {"qa": 2, "segment": 1}}}]
    got = o.list_file_names("idx", keyword="TikTok", size=50, from_type_norm="document")
    query = o.engine.agg_terms.call_args[0][1]
    dumped = json.dumps(query, ensure_ascii=False)
    assert "from_type_norm" in dumped and "wildcard" in dumped
    assert got == [{"value": "a.pdf", "doc_count": 3,
                    "type_count": {"qa": 2, "segment": 1}}]


# ---------------- match_mode 严格二选一，无兜底 ----------------

def test_exact_never_falls_back_to_fuzzy():
    """exact 查不到就是查不到，绝不能偷偷转模糊。"""
    o = _iface()
    o.engine.count_by_query.return_value = 0
    r = o.resolve_file_name("idx", "不存在的文件.pdf", match_mode="exact")
    assert r["matched"] is False and r["doc_count"] == 0
    assert "精确匹配无结果" in r["reason"]
    o.engine.agg_terms.assert_not_called(), "exact 模式不得发起模糊召回"


def test_exact_uses_keyword_term_only():
    o = _iface()
    o.engine.count_by_query.return_value = 7
    r = o.resolve_file_name("idx", "Text.docx", match_mode="exact")
    assert r == {"matched": True, "matched_name": "Text.docx", "doc_count": 7,
                 "dice": 1.0, "reason": None}
    q = o.engine.count_by_query.call_args[0][1]
    dumped = json.dumps(q, ensure_ascii=False)
    assert "ext_info.from_file_name.keyword" in dumped
    # exact 不得发起模糊查询。注意不能用裸子串判 "match"——
    # 文件名现在是 should(OR) 结构，里面合法地含有 "minimum_should_match"。
    assert "wildcard" not in dumped
    assert '"match"' not in dumped and '"fuzziness"' not in dumped


def test_fuzzy_never_falls_back_to_exact():
    """fuzzy 达不到阈值就是没找到，不得退回 term 精确查询。"""
    o = _iface()
    o.engine.agg_terms.return_value = [{"key": "完全不相干的文件.pdf", "doc_count": 5}]
    r = o.resolve_file_name("idx", "Text.docx", match_mode="fuzzy")
    assert r["matched"] is False
    assert "未达阈值" in r["reason"]
    o.engine.count_by_query.assert_not_called(), "fuzzy 模式不得回退到精确计数"


def test_fuzzy_picks_highest_dice_above_threshold():
    """取 Dice 最大的那个，且必须 >= 0.9。"""
    o = _iface()
    o.engine.agg_terms.return_value = [
        {"key": "ManoMano卖家操作指南 第二讲新手入门.pdf", "doc_count": 220},
        {"key": "ManoMano卖家操作指南 第一讲上线准备.pdf", "doc_count": 100},
    ]
    r = o.resolve_file_name("idx", "ManoMano卖家操作指南 第二讲新手入门.pdf", match_mode="fuzzy")
    assert r["matched"] is True
    assert r["matched_name"] == "ManoMano卖家操作指南 第二讲新手入门.pdf"
    assert r["dice"] >= 0.9


def test_invalid_match_mode_is_rejected():
    o = _iface()
    r = o.resolve_file_name("idx", "a.pdf", match_mode="smart")
    assert r["matched"] is False and "exact 或 fuzzy" in r["reason"]


# ---------------- 两个 ES 限制 ----------------

def test_wildcard_fragment_respects_max_wildcard_length():
    """index.max_wildcard_length=50，超长文件名直接拿全名做 *name* 会 400。"""
    o = _iface()
    long_name = "https://seller.tiktokglobalshop.com/university/home?identity=1&role=x" * 2
    o.engine.agg_terms.return_value = []
    o.resolve_file_name("idx", long_name, match_mode="fuzzy")
    dumped = json.dumps(o.engine.agg_terms.call_args[0][1], ensure_ascii=False)
    value = json.loads(dumped)["bool"]["should"][0]["wildcard"][
        "ext_info.from_file_name.keyword"]["value"]
    assert len(value) <= SearchDataInterface.MAX_WILDCARD_FRAGMENT + 2


def test_wildcard_special_chars_escaped():
    """实测 51 个文件名含 ( ) | & 等；* ? 必须转义，避免被当成通配。"""
    o = _iface()
    o.engine.agg_terms.return_value = []
    o.resolve_file_name("idx", "报告*草稿?(1).pdf", match_mode="fuzzy")
    value = o.engine.agg_terms.call_args[0][1]["bool"]["should"][0]["wildcard"][
        "ext_info.from_file_name.keyword"]["value"]
    assert "\\*" in value and "\\?" in value


def test_overlong_filename_rejected_not_silently_zero():
    """>256 触发 keyword 的 ignore_above：term 永远查不到且不报错。

    必须显式拦下来，否则用户以为删了、其实一条没删。
    """
    o = _iface()
    r = o.resolve_file_name("idx", "x" * 300, match_mode="exact")
    assert r["matched"] is False and "未被索引为 keyword" in r["reason"]
    o.engine.count_by_query.assert_not_called()


# ---------------- preview ----------------

def test_preview_warns_when_fuzzy_matched_other_name():
    """模糊匹配到的是别的名字时必须警告，由用户确认。"""
    o = _iface()
    o.engine.agg_terms.return_value = [{"key": "入驻会议_260724ver.pdf", "doc_count": 267}]
    o.engine.count_by_query.return_value = 267
    r = o.preview_delete_by_file("idx", ["入驻会议_260724ver.pd"], match_mode="fuzzy")
    assert any("模糊匹配到" in w for w in r["warnings"])
    assert r["by_file"][0]["matched_name"] == "入驻会议_260724ver.pdf"


def test_preview_reports_unmatched_file_without_aborting_others():
    """一个文件名没匹配上，不能影响其它文件名的统计。"""
    o = _iface()
    # 调用序：resolve(缺失)=0 → resolve(存在)=5 → 该文件明细计数 → 汇总计数
    o.engine.count_by_query.side_effect = lambda idx, q: (
        0 if "缺失.pdf" in json.dumps(q, ensure_ascii=False) else 5)
    o.engine.agg_terms.return_value = []
    r = o.preview_delete_by_file("idx", ["缺失.pdf", "存在.pdf"], match_mode="exact")
    assert r["by_file"][0]["matched"] is False
    assert r["by_file"][1]["matched"] is True
    assert r["resolved_names"] == ["存在.pdf"], "只有匹配上的才进入删除范围"
    assert r["total_count"] == 5
    assert any("缺失.pdf" in w for w in r["warnings"])


# ---------------- 删除 ----------------

def test_delete_takes_same_params_as_preview():
    """delete 与 preview 入参一致，区别只是这个真删。

    服务端不强制「必须先预览」——是否让用户确认由前端流程决定。
    """
    import inspect
    dsig = set(inspect.signature(SearchDataInterface.delete_by_file).parameters)
    psig = set(inspect.signature(SearchDataInterface.preview_delete_by_file).parameters)
    assert {"index_name", "file_names", "match_mode", "data_types", "audit_results"} <= dsig
    # delete 不该再要求 preview 产物
    assert "confirm_token" not in dsig and "expected_count" not in dsig
    # 两者只差 sample_size（预览用）和 snapshot_dir（删除用）
    assert psig - dsig == {"sample_size"}


def test_delete_soft_deletes_and_snapshots():
    o = _iface()
    o.engine.count_by_query.return_value = 10
    o.engine.agg_terms.return_value = []
    o.engine.update_by_query.return_value = {"updated": 10, "total": 10,
                                             "version_conflicts": 0, "failures": []}
    with mock.patch.object(SearchDataInterface, "_dump_snapshot",
                           return_value="/tmp/snap.jsonl") as snap:
        r = o.delete_by_file(index_name="idx", file_names=["a.pdf"])
    snap.assert_called_once(), "删除前必须写快照"
    assert r["success"] is True and r["deleted_count"] == 10
    fields = o.engine.update_by_query.call_args[0][2]
    assert fields == {"del_flag": 1}, "只做软删，不得硬删"


def test_delete_aborts_when_nothing_matched():
    """一个文件名都没匹配上时不执行删除，避免空条件误删全库。"""
    o = _iface()
    o.engine.count_by_query.return_value = 0
    o.engine.agg_terms.return_value = []
    r = o.delete_by_file(index_name="idx", file_names=["缺失.pdf"])
    assert r["success"] is False
    o.engine.update_by_query.assert_not_called()


def test_delete_reports_version_conflicts():
    o = _iface()
    o.engine.count_by_query.return_value = 5
    o.engine.agg_terms.return_value = []
    o.engine.update_by_query.return_value = {"updated": 3, "total": 5,
                                             "version_conflicts": 2, "failures": []}
    with mock.patch.object(SearchDataInterface, "_dump_snapshot", return_value="/tmp/s"):
        r = o.delete_by_file(index_name="idx", file_names=["a.pdf"])
    assert r["deleted_count"] == 3
    assert "版本冲突" in r["message"]


def test_delete_query_carries_scope_and_filters():
    o = _iface()
    o.engine.count_by_query.return_value = 4
    o.engine.agg_terms.return_value = []
    o.engine.update_by_query.return_value = {"updated": 4, "total": 4,
                                             "version_conflicts": 0, "failures": []}
    with mock.patch.object(SearchDataInterface, "_dump_snapshot", return_value="/tmp/s"):
        o.delete_by_file(index_name="idx", file_names=["a.pdf"], data_types=["qa"])
    dumped = json.dumps(o.engine.update_by_query.call_args[0][1], ensure_ascii=False)
    assert "from_type_norm" in dumped and "del_flag" in dumped
    assert '"data_type"' in dumped


def test_delete_fuzzy_deletes_matched_name_not_input():
    """fuzzy 下真正删的是匹配到的完整文件名，不是用户输入的那个。"""
    o = _iface()
    o.engine.agg_terms.side_effect = (
        lambda idx, q, field, **kw: [{"key": "Text.docx", "doc_count": 149}]
        if field == SearchDataInterface.FILE_NAME_KEYWORD else [])
    o.engine.count_by_query.return_value = 149
    o.engine.update_by_query.return_value = {"updated": 149, "total": 149,
                                             "version_conflicts": 0, "failures": []}
    with mock.patch.object(SearchDataInterface, "_dump_snapshot", return_value="/tmp/s"):
        o.delete_by_file(index_name="idx", file_names=["Text.docxx"], match_mode="fuzzy")
    dumped = json.dumps(o.engine.update_by_query.call_args[0][1], ensure_ascii=False)
    assert "Text.docx" in dumped and "Text.docxx" not in dumped


# ---------------- Dice ----------------

@pytest.mark.parametrize("a,b,expect", [
    ("abc.pdf", "abc.pdf", 1.0),
    ("", "", 1.0),
])
def test_dice_identical(a, b, expect):
    assert SearchDataInterface.dice_similarity(a, b) == expect


def test_dice_separates_unrelated_names():
    """子串关系不等于相似：'Noon' 与客户群文件名 Dice 很低，不会被模糊误选。"""
    s = SearchDataInterface.dice_similarity("Noon", "Free-Noon-99646294-GC# 24731")
    assert s < 0.9


# ---------------- supersedes：重跑换名后仍能一起删 ----------------

def test_query_matches_supersedes_file_name():
    """文件名要同时匹配 from_file_name 与 supersedes_file_name。

    文档重跑后新知识换了文件名（wayfair 实测：旧名带分类前缀「基础运营_xxx.docx」，
    新包同一篇叫「xxx.docx」）。前端按旧文件名删除时必须能连新知识一起删掉，
    否则旧的删了新的还在，等于没更新干净。
    """
    o = _iface()
    q = o._build_file_query(["基础运营_管理我的团队页面.docx"])
    dumped = json.dumps(q, ensure_ascii=False)
    assert SearchDataInterface.FILE_NAME_KEYWORD in dumped
    assert SearchDataInterface.SUPERSEDES_FIELD_KEYWORD in dumped
    # 必须是 OR，不是 AND——AND 会导致两个字段都要命中，几乎永远查不到
    should = None
    for m in q["bool"]["must"]:
        if isinstance(m, dict) and "bool" in m and "should" in m["bool"]:
            should = m["bool"]
    assert should is not None, "文件名匹配应该是 should(OR) 结构"
    assert should.get("minimum_should_match") == 1


def test_supersedes_does_not_break_other_filters():
    """加了 supersedes 之后，来源白名单/del_flag/类型过滤仍然生效。"""
    o = _iface()
    q = o._build_file_query(["a.pdf"], data_types=["qa"], audit_results=[2])
    dumped = json.dumps(q, ensure_ascii=False)
    assert "from_type_norm" in dumped and "del_flag" in dumped
    assert '"data_type"' in dumped and '"audit_result"' in dumped
