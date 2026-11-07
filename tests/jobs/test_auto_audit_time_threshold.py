from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""timing_auto_audit_kg 的时间阈值解析测试。

只测纯函数，不连 ES：脚本模块顶层 import elasticsearch，所以用 importlib 按路径加载前
先确认依赖可用，缺失时跳过（本地无 ES client 也能跑其余测试）。
"""
import importlib.util
import os

import pytest

SCRIPT = str(_PROJECT_ROOT / 'src/kdb/jobs/auto_audit.py')


@pytest.fixture(scope="module")
def mod():
    pytest.importorskip("elasticsearch", reason="需要 elasticsearch client 才能导入被测脚本")
    spec = importlib.util.spec_from_file_location("timing_auto_audit_kg", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_both_absent_falls_back_to_legacy_24h(mod):
    assert mod.resolve_time_threshold(None, None) == (24, 0)


def test_minutes_only_does_not_inherit_the_24h_default(mod):
    # 回归点：--minutes 10 必须是 10 分钟，不能被 --hours 的旧默认值顶成 24 小时 10 分钟
    assert mod.resolve_time_threshold(None, 10) == (0, 10)


def test_hours_only(mod):
    assert mod.resolve_time_threshold(2, None) == (2, 0)


def test_hours_and_minutes_add_up(mod):
    assert mod.resolve_time_threshold(1, 30) == (1, 30)


def test_explicit_zero_hours_means_no_delay(mod):
    assert mod.resolve_time_threshold(0, None) == (0, 0)


def test_negative_is_rejected(mod):
    with pytest.raises(ValueError):
        mod.resolve_time_threshold(-1, None)


@pytest.mark.parametrize("hours,minutes,expected", [
    (24, 0, "24小时"),
    (0, 10, "10分钟"),
    (1, 30, "1小时30分钟"),
])
def test_format_time_window(mod, hours, minutes, expected):
    assert mod.format_time_window(hours, minutes) == expected


def test_format_time_window_zero_is_explicit(mod):
    assert "不设延迟" in mod.format_time_window(0, 0)


def test_update_by_query_uses_scroll_size_without_max_docs(mod):
    class FakeEs:
        def __init__(self):
            self.update_kwargs = None

        def update_by_query(self, **kwargs):
            self.update_kwargs = kwargs
            return {"updated": 3, "total": 3, "failures": []}

    from kdb.retrieval.engines.es_maintenance import run_native_update
    client = FakeEs()
    result = run_native_update(client, {"index": "idx", "body": {"query": {"match_all": {}}},
                                       "wait_for_completion": True}, scroll_size=30, client_api=7)
    assert client.update_kwargs["wait_for_completion"] is True
    assert client.update_kwargs["scroll_size"] == 30
    assert client.update_kwargs["request_timeout"] == 3600
    assert "max_docs" not in client.update_kwargs
    assert result["updated"] == 3
    assert result["failures"] == []


def test_process_one_data_keeps_machine_approved_audit_result():
    pytest.importorskip("elasticsearch", reason="需要项目依赖才导入 SearchDataInterface")
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface

    processor = SearchDataInterface.__new__(SearchDataInterface)
    processor.doc_schema_field = {
        "title", "synonyms_title", "content", "data_type", "platform",
        "audit_result", "quality_level", "keywords", "indexes",
        "insert_time", "update_time", "from_type", "ext_info", "_id",
        "title_embedding", "content_embedding", "image_indexes", "del_flag",
        "from_type_norm", "category_infos", "client", "primary_category",
        "dataset", "task_id", "multimodal_contents", "index_name",
    }

    data = {
        "_id": "doc1",
        "data_type": "segment",
        "audit_result": 2,
        "quality_level": "high",
        "insert_time": "2026-08-27 00:00:00",
        "from_type": "html",
        "from_type_norm": "html",
        "del_flag": 0,
    }

    assert processor.process_one_data(data, index_name="idx") is True
    assert data["audit_result"] == 2
