"""
_ensure_index / update_index_map / _mapping_config_equal 的回归测试。

背景：线上 ES 7.10 的 dense_vector 只支持 dims，代码 mapping 里写的
similarity/index 会被静默丢弃，导致 update_index_map 对每个索引都判「配置发生变化」
→ has_build_index 永远不置位 → 每次检索都重跑 _ensure_index（每索引 3 次 ES 往返）。
"""
import sys
import types
from unittest import mock

import pytest

# es_search_interface 依赖 elasticsearch 包，测试环境不一定有，先打桩
if "elasticsearch" not in sys.modules:
    stub = types.ModuleType("elasticsearch")
    stub.Elasticsearch = object
    sys.modules["elasticsearch"] = stub

from kdb.retrieval.engines.providers.es7 import EsSearchInterfaceOri
from kdb.retrieval.engines.mapping_comparison import _mapping_config_equal


# ---------- _mapping_config_equal ----------

def test_ignores_similarity_not_supported_by_es710():
    """dense_vector 的 similarity 在 ES 7.10 会被丢弃，不能算差异"""
    expected = {"type": "dense_vector", "dims": 1024, "similarity": "cosine"}
    existing = {"type": "dense_vector", "dims": 1024}
    assert _mapping_config_equal(expected, existing)


def test_ignores_index_key():
    expected = {"type": "dense_vector", "dims": 1024, "index": False}
    existing = {"type": "dense_vector", "dims": 1024}
    assert _mapping_config_equal(expected, existing)


def test_object_type_not_echoed_by_es():
    """ES 对 object 类型不回显 type 字段"""
    assert _mapping_config_equal({"type": "object"}, {"properties": {"a": {"type": "keyword"}}})


def test_nested_properties_compared_recursively():
    """整体 != 会因为孙字段的 similarity 判不等；递归比对应当相等"""
    expected = {
        "type": "nested",
        "properties": {
            "text": {"type": "text", "analyzer": "ik_max_word"},
            "embedding": {"type": "dense_vector", "dims": 1024, "similarity": "cosine"},
        },
    }
    existing = {
        "type": "nested",
        "properties": {
            "embedding": {"type": "dense_vector", "dims": 1024},
            "text": {"type": "text", "analyzer": "ik_max_word"},
        },
    }
    assert _mapping_config_equal(expected, existing)


def test_real_conflict_still_detected():
    """task_id: 线上 text vs 代码 keyword，是真冲突，必须判不等"""
    assert not _mapping_config_equal({"type": "keyword"}, {"type": "text"})


def test_dims_mismatch_still_detected():
    expected = {"type": "dense_vector", "dims": 1024, "similarity": "cosine"}
    existing = {"type": "dense_vector", "dims": 512}
    assert not _mapping_config_equal(expected, existing)


def test_missing_field_is_not_equal():
    assert not _mapping_config_equal({"type": "keyword"}, None)


# ---------- update_index_map ----------

def _make_iface(existing_properties):
    """造一个只有 self.es 的壳，避开 __init__ 里的真实 ES 连接"""
    iface = EsSearchInterfaceOri.__new__(EsSearchInterfaceOri)
    iface.has_build_index = {}
    iface.auto_update_mapping = True   # 默认关，测 put_mapping 行为时显式打开
    iface.es = mock.MagicMock()
    iface.es.indices.exists.return_value = True
    iface.es.indices.get_mapping.return_value = {
        "idx": {"mappings": {"properties": existing_properties}}
    }
    return iface


def test_conflict_does_not_block_new_field():
    """真冲突(task_id)不应该连坐掉本该新增的 categorys_info —— 改之前就是这个 bug"""
    iface = _make_iface({"task_id": {"type": "text"}})
    new_mapping = {
        "properties": {
            "task_id": {"type": "keyword"},          # 真冲突，跳过
            "categorys_info": {"type": "object", "enabled": False},  # 缺失，应补上
        }
    }
    assert iface.update_index_map("idx", new_mapping) is True
    iface.es.indices.put_mapping.assert_called_once()
    body = iface.es.indices.put_mapping.call_args.kwargs["body"]
    assert list(body["properties"]) == ["categorys_info"]


def test_no_change_needed_returns_true_without_put_mapping():
    iface = _make_iface({"title": {"type": "text", "analyzer": "ik_max_word"}})
    new_mapping = {"properties": {"title": {"type": "text", "analyzer": "ik_max_word"}}}
    assert iface.update_index_map("idx", new_mapping) is True
    iface.es.indices.put_mapping.assert_not_called()


def test_put_mapping_failure_returns_false():
    iface = _make_iface({})
    iface.es.indices.put_mapping.side_effect = RuntimeError("boom")
    assert iface.update_index_map("idx", {"properties": {"a": {"type": "keyword"}}}) is False


# ---------- _ensure_index 的缓存 ----------

def test_ensure_index_runs_once_per_index():
    """核心回归：第二次调用必须直接返回，不再打 ES"""
    iface = _make_iface({})
    iface.vector_fields = {"indexes_embedding": 1024}

    iface._ensure_index("mercado_local")
    calls_after_first = iface.es.indices.exists.call_count
    assert calls_after_first > 0
    assert "mercado_local" in iface.has_build_index

    iface._ensure_index("mercado_local")
    assert iface.es.indices.exists.call_count == calls_after_first


def test_ensure_index_caches_even_when_mapping_conflicts():
    """mapping 有不可修复的冲突时也要置位——重试永远不会成功"""
    iface = _make_iface({"task_id": {"type": "text"}})
    iface.vector_fields = {"indexes_embedding": 1024}
    with mock.patch.object(iface, "update_index_map", return_value=False):
        iface._ensure_index("mercado")
    assert "mercado" in iface.has_build_index


def test_ensure_index_does_not_cache_on_exception():
    """建索引失败要保留重试机会"""
    iface = _make_iface({})
    iface.vector_fields = {"indexes_embedding": 1024}
    iface.es.indices.exists.side_effect = RuntimeError("es down")
    with pytest.raises(RuntimeError):
        iface._ensure_index("newidx")
    assert "newidx" not in iface.has_build_index


# ---------- _get_index_name 的 key 对齐 ----------

def test_get_index_name_cache_key_is_case_insensitive():
    """大写索引名过去永远命中不了缓存，每次都重跑"""
    iface = _make_iface({})
    iface.vector_fields = {"indexes_embedding": 1024}
    iface.index_name = "default"

    with mock.patch.object(iface, "_ensure_index", wraps=iface._ensure_index) as spy:
        iface._get_index_name(["Mercado_Local"])
        iface._get_index_name(["Mercado_Local"])
        assert spy.call_count == 1


def test_get_index_name_splits_comma_string():
    """str 形式的多索引串必须拆开，不能拿 'a,b' 整串去 _ensure_index"""
    iface = _make_iface({})
    iface.vector_fields = {"indexes_embedding": 1024}
    iface.index_name = "default"

    with mock.patch.object(iface, "_ensure_index") as spy:
        result = iface._get_index_name("mercado_local,mercado_local_mercado_local_admin")
        assert result == "mercado_local,mercado_local_mercado_local_admin"
        assert [c.args[0] for c in spy.call_args_list] == [
            "mercado_local",
            "mercado_local_mercado_local_admin",
        ]


def test_auto_update_mapping_off_skips_put_mapping():
    """默认不开时，只记录缺失字段，绝不写线上 mapping"""
    iface = _make_iface({})
    iface.auto_update_mapping = False
    assert iface.update_index_map("idx", {"properties": {"categorys_info": {"type": "object"}}}) is True
    iface.es.indices.put_mapping.assert_not_called()
