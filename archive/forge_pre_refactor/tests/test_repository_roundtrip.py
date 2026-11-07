"""Repository 纯向量 CRUD 回环测试。

不走文本→向量化的便利路径，直接给 Repository 一份"向量已就绪"的 prepared 文档，
验证：insert→get→search_multi→update_by_id→update_by_condition→delete 全链路行为。
覆盖软删除（默认搜索过滤、显式 del_flag=1 仍可见）。
"""

import time
from datetime import datetime

import pytest

from tests.conftest import (
    wait_for_absent,
    wait_for_field,
    wait_for_present,
    wait_for_search_hit,
)

pytestmark = pytest.mark.integration

PLATFORM = "kdb_repo_rt"
DATA_TYPE = "qa"


def _build_prepared_doc(embedding_client, repo_default_index):
    """构造一条向量已就绪的 prepared 文档（不走 service 的 _prepare_document）。"""
    title = "kdb repo rt：忘记密码怎么办？"
    content = "在登录页点击『忘记密码』，按邮箱链接重置即可。"
    custom_extra = {"trace": "repo_rt_case_1"}

    title_emb = embedding_client.text2embedding(title).tolist()
    content_emb = embedding_client.text2embedding(content).tolist()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 用与 service.gen_data_id 一致的算法，确保 _id 可控
    from kdb.crud.ids import gen_data_id
    _id = gen_data_id({"title": title, "content": content, "data_type": DATA_TYPE})

    doc = {
        "_id": _id,
        "title": title,
        "content": content,
        "data_type": DATA_TYPE,
        "platform": PLATFORM,
        "audit_result": 1,
        "quality_level": "high",
        "from_type": "chat",
        "del_flag": 0,  # Repository 是纯向量层；本字段必须由调用方提供（这里直接给）
        "title_embedding": title_emb,
        "content_embedding": content_emb,
        "indexes": [{"text": title, "embedding": title_emb}],
        "ext_info": custom_extra,
        "insert_time": now,
        "update_time": now,
    }
    return doc, _id


def test_repository_full_crud_roundtrip(repo, embedding_client, test_index, cleanup_ids):
    doc, _id = _build_prepared_doc(embedding_client, test_index)
    cleanup_ids.append(_id)

    # ---- Create ----
    assert repo.insert(doc, index_name=test_index, refresh_imm=True) is True

    # ---- Read: get（容忍 serverless 写入可见延迟）----
    got = wait_for_present(repo, _id, test_index)
    assert got is not None
    assert got["_id"] == _id
    assert got["title"] == doc["title"]
    assert got["content"] == doc["content"]
    assert got["data_type"] == DATA_TYPE
    assert got["platform"] == PLATFORM
    assert got["del_flag"] == 0
    assert len(got["title_embedding"]) == 1024
    assert len(got["content_embedding"]) == 1024
    assert len(got["indexes"]) == 1
    assert len(got["indexes"][0]["embedding"]) == 1024
    assert got["ext_info"] == {"trace": "repo_rt_case_1"}

    # ---- Read: search_multi (vector + text + attribute) ----
    q_emb = embedding_client.text2embedding("密码忘了怎么办")
    query_dict = {
        "query": "密码忘了怎么办",
        "vector": {"value": q_emb},
        "attribute": [{"data_type": [DATA_TYPE], "platform": [PLATFORM]}],
    }
    # 等待搜索可见（refresh 延迟比 get 长）
    hit_doc = wait_for_search_hit(repo, _id, query_dict, test_index)
    assert hit_doc["_id"] == _id
    assert "score" in hit_doc

    # ---- Update by _id（局部合并 + 强制刷新）----
    new_content = "去 设置→账户安全→重置密码，按手机号验证。"
    new_content_emb = embedding_client.text2embedding(new_content).tolist()
    assert (
        repo.update_by_id(
            _id,
            {"content": new_content, "content_embedding": new_content_emb},
            index_name=test_index,
            refresh=True,
        )
        is True
    )
    got2 = wait_for_field(repo, _id, "content", new_content, test_index)
    assert got2["title"] == doc["title"]  # 未改动字段保留

    # ---- Update by condition（软删除 del_flag=1）----
    assert (
        repo.update_by_condition(
            {"del_flag": 1},
            [{"platform": [PLATFORM]}],
            index_name=test_index,
            refresh=True,
        )
        is True
    )
    wait_for_field(repo, _id, "del_flag", 1, test_index)

    # 默认 search_multi 注入 del_flag=0 过滤 → 该 doc 应不可见
    hits_soft, _ = repo.search_multi(query_dict, index_name=test_index, size=10)
    assert all(d.get("_id") != _id for d in hits_soft), "软删除后默认搜索仍可见，过滤未生效"

    # 显式带 del_flag=1 应能查到
    query_dict_with_softdel = {
        **query_dict,
        "attribute": [{"data_type": [DATA_TYPE], "platform": [PLATFORM], "del_flag": [1]}],
    }
    hits_explicit, _ = repo.search_multi(query_dict_with_softdel, index_name=test_index, size=10)
    assert any(d.get("_id") == _id for d in hits_explicit), "显式 del_flag=1 仍查不到"

    # ---- Delete ----
    assert repo.delete(_id, index_name=test_index, refresh=True) is True
    wait_for_absent(repo, _id, test_index)  # serverless 删除可见窗口
    cleanup_ids.remove(_id)  # 已删，避免 teardown 重复


def test_repository_get_missing_returns_none(repo, test_index):
    """不存在的 _id：get 返回 None（不抛异常）。"""
    assert repo.get("nonexistent_id_kdb_rt_xxx", index_name=test_index) is None


def test_repository_insert_requires_id(repo, test_index):
    """前置约定违反（无 _id）：旧 engine.insert 内部 ValueError → 返回 False。"""
    bad = {"title": "no id", "content": "x", "data_type": "qa", "platform": PLATFORM}
    assert repo.insert(bad, index_name=test_index, refresh_imm=True) is False
