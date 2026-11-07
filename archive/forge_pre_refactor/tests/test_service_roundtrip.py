"""Service 文本级 CRUD 回环测试。

文本输入直接进 Service，让其内部完成向量化、_id 生成、时间字段填充、ext_info 归集。
验证：insert_text→get→search_text→update→delete 全链路行为。
"""

import time

import pytest

from tests.conftest import (
    wait_for_absent,
    wait_for_field,
    wait_for_present,
    wait_for_search_hit,
)

pytestmark = pytest.mark.integration

PLATFORM = "kdb_svc_rt"


def _input_doc():
    return {
        "title": "kdb svc rt：如何注销账号？",
        "content": "去 设置→账户管理→注销账号，按指引完成。",
        "data_type": "qa",
        "platform": PLATFORM,
        "audit_result": 1,
        "quality_level": "high",
        "from_type": "chat",
        "synonyms_title": ["如何销户", "如何关闭账号"],
        # 非 schema 字段，应进 ext_info
        "trace_id": "svc_rt_case_1",
        "client_extra": "should_go_to_ext_info",
    }


def test_service_full_text_crud_roundtrip(service, repo, embedding_client, test_index, cleanup_ids):
    inp = _input_doc()

    # 预测的 _id（service.gen_data_id == 旧 gen_data_id）
    from kdb.crud.ids import gen_data_id
    expected_id = gen_data_id(
        {"title": inp["title"], "content": inp["content"], "data_type": inp["data_type"]}
    )
    cleanup_ids.append(expected_id)

    # ---- insert_text ----
    ok, msg = service.insert_text(dict(inp), index_name=test_index, refresh_imm=True)
    assert ok, f"insert_text 失败：{msg}"

    # ---- get：验证向量化、归集、时间、del_flag、_id（容忍 serverless 写入可见延迟）----
    stored = wait_for_present(service._repo, expected_id, test_index)
    assert stored is not None and stored["_id"] == expected_id
    assert stored["title"] == inp["title"]
    assert stored["content"] == inp["content"]
    assert stored["data_type"] == "qa"
    assert stored["platform"] == PLATFORM
    assert stored["del_flag"] == 0, "新建文档必须自动填 del_flag=0（底层引擎契约）"
    # 时间字段存在
    assert "insert_time" in stored and isinstance(stored["insert_time"], str)
    assert "update_time" in stored and isinstance(stored["update_time"], str)
    # 向量维度
    assert len(stored["title_embedding"]) == 1024
    assert len(stored["content_embedding"]) == 1024
    # indexes 冗余构造：title + 同义题 = 3 项
    idx_texts = {idx["text"] for idx in stored["indexes"]}
    assert inp["title"] in idx_texts
    assert "如何销户" in idx_texts and "如何关闭账号" in idx_texts
    for idx in stored["indexes"]:
        assert len(idx["embedding"]) == 1024
    # 非 schema 字段归集到 ext_info；schema 字段不进 ext_info
    assert stored["ext_info"].get("trace_id") == "svc_rt_case_1"
    assert stored["ext_info"].get("client_extra") == "should_go_to_ext_info"
    assert "title" not in stored["ext_info"]

    # ---- search_text ----
    # 用 wait_for 等搜索可见
    def _do_search():
        ds, _ = service.search_text(
            "怎么销户",
            index_name=test_index,
            condition_dicts=[{"data_type": ["qa"], "platform": [PLATFORM]}],
            size=5,
            search_type="qa",
            use_synonyms=True,
        )
        for d in ds:
            if d.get("_id") == expected_id:
                return ds
        return False
    docs = _do_search() or _do_search()  # 即跑即查；若首次未命中则再试一次
    if not docs:
        import time as _t
        for _ in range(20):
            _t.sleep(0.5)
            docs = _do_search()
            if docs:
                break
    assert docs, f"search_text 未命中刚插入的文档（id={expected_id}）"
    found = [d for d in docs if d.get("_id") == expected_id]
    assert len(found) == 1
    assert "similarity" in found[0] and 0 < found[0]["similarity"] <= 2.0
    # 旧 search_data_by_query 拉 size*2 候选，不排序不截断（Service 已对齐）
    assert len(docs) <= 5 * 2

    # ---- update：改 content + 重算向量 + 强制刷新 ----
    new_content = "去 我的→设置→账号安全→注销，72 小时内可撤销。"
    assert service.update(
        expected_id,
        {"content": new_content},
        index_name=test_index,
        regenerate_embedding=True,
        refresh=True,
    ) is True
    stored2 = wait_for_field(service._repo, expected_id, "content", new_content, test_index)
    assert len(stored2["content_embedding"]) == 1024
    # update_time 已刷新（字符串可比较）
    assert stored2["update_time"] >= stored["update_time"]
    # 未传字段保留
    assert stored2["title"] == inp["title"]

    # ---- delete ----
    assert service.delete(expected_id, index_name=test_index, refresh=True) is True
    wait_for_absent(service._repo, expected_id, test_index)
    cleanup_ids.remove(expected_id)


def test_service_segment_drops_title(service, test_index, cleanup_ids):
    """data_type=segment：title/synonyms_title 应被去掉；_id 用 (空title, content, segment) 算出。"""
    inp = {
        "title": "should be dropped",
        "synonyms_title": ["also dropped"],
        "content": "kdb svc rt segment 测试内容。",
        "data_type": "segment",
        "platform": PLATFORM,
        "from_type": "doc",
    }
    from kdb.crud.ids import gen_data_id
    expected_id = gen_data_id({"title": "", "content": inp["content"], "data_type": "segment"})
    cleanup_ids.append(expected_id)

    ok, _ = service.insert_text(dict(inp), index_name=test_index, refresh_imm=True)
    assert ok
    stored = wait_for_present(service._repo, expected_id, test_index)
    assert stored is not None
    assert stored.get("title") in (None, "")
    assert "synonyms_title" not in stored or not stored["synonyms_title"]
    assert stored["content"] == inp["content"]
    assert len(stored["content_embedding"]) == 1024


def test_service_ext_info_routing(service, test_index, cleanup_ids):
    """schema 字段全部进 top-level；非 schema 字段全部进 ext_info。"""
    inp = {
        "title": "kdb svc rt ext routing",
        "content": "x",
        "data_type": "qa",
        "platform": PLATFORM,
        "audit_result": 1,
        "quality_level": "high",
        "from_type": "chat",
        "foo": 1,
        "bar": "baz",
        "nested": {"a": [1, 2]},
    }
    from kdb.crud.ids import gen_data_id
    _id = gen_data_id({"title": inp["title"], "content": inp["content"], "data_type": "qa"})
    cleanup_ids.append(_id)
    ok, _ = service.insert_text(dict(inp), index_name=test_index, refresh_imm=True)
    assert ok
    stored = wait_for_present(service._repo, _id, test_index)
    assert stored is not None
    # schema 字段都在 top
    for k in ["title", "content", "data_type", "platform", "audit_result", "quality_level", "from_type"]:
        assert k in stored
    # 非 schema 字段归 ext_info
    ext = stored.get("ext_info", {})
    assert ext.get("foo") == 1
    assert ext.get("bar") == "baz"
    assert ext.get("nested") == {"a": [1, 2]}


def test_audit_result_2_preserved_on_insert(service, test_index, cleanup_ids):
    """audit_result=2 是合法已审核态（旧实现 si:476 合法集 [-1,0,1,2]，检索契约
    audit_result∈[1,2] 依赖），插入/upsert 不得被"非法值矫正"重置为 -1。
    回归：2026-09-02 VALID_AUDIT_RESULTS 抄漏 2，生产 upsert 把 audit=2 的 doc 静默降为 -1。"""
    from kdb.crud.ids import gen_data_id

    inp = _input_doc()
    inp["title"] = "kdb svc rt：audit=2 保持用例"
    inp["audit_result"] = 2
    expected_id = gen_data_id(
        {"title": inp["title"], "content": inp["content"], "data_type": inp["data_type"]}
    )
    cleanup_ids.append(expected_id)

    ok, msg = service.insert_text(dict(inp), index_name=test_index, refresh_imm=True)
    assert ok, f"insert_text 失败：{msg}"
    stored = wait_for_present(service._repo, expected_id, test_index)
    assert stored["audit_result"] == 2, "合法值 2 被矫正逻辑误伤"

    # 对照：真正的非法值仍应矫正为 -1
    inp2 = _input_doc()
    inp2["title"] = "kdb svc rt：audit 非法值矫正用例"
    inp2["audit_result"] = 99
    bad_id = gen_data_id(
        {"title": inp2["title"], "content": inp2["content"], "data_type": inp2["data_type"]}
    )
    cleanup_ids.append(bad_id)
    ok, msg = service.insert_text(dict(inp2), index_name=test_index, refresh_imm=True)
    assert ok, f"insert_text 失败：{msg}"
    stored2 = wait_for_present(service._repo, bad_id, test_index)
    assert stored2["audit_result"] == -1, "非法值 99 未被矫正"
