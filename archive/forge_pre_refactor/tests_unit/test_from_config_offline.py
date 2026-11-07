"""`KnowledgeService.from_config` 分支离线测试（审计建议 4）。

monkeypatch 掉 Repository/embedding 构造（不连 ES / DashScope），验证：
- legacy_search_config_path 存在：multimodal_prefix / check_duplicate / is_need_llm /
  category_service_url 全部从旧 config 装载；
- 缺 legacy_search_config_path：prefix 为空 + **告警**（不再静默）；
- 索引解析：显式参数 > default_index_name > test_index_name（告警）> engine 兜底（告警）。
"""

import json
import logging

import pytest

from tests_unit.conftest import FakeEmbedding, FakeEngine


class _FakeRepo:
    def __init__(self, engine=None, engine_config_path=None, default_index=None):
        self.engine_config_path = engine_config_path
        self._default_index = default_index or "engine_default_idx"


@pytest.fixture()
def patched_service(monkeypatch):
    import kdb.crud.service as svc_mod

    monkeypatch.setattr(svc_mod, "KnowledgeRepository", _FakeRepo)
    monkeypatch.setattr(svc_mod, "build_embedding_client", lambda path: FakeEmbedding())
    return svc_mod


def _write_cfg(tmp_path, *, with_legacy=True, legacy_overrides=None, **cfg_extra):
    legacy_cfg_path = tmp_path / "config_for_search_index.json"
    if with_legacy:
        legacy_cfg = {
            "multimodal_prefix": "https://file.example.com/",
            "check_duplicate": False,
            "is_need_llm": True,
            "category_service_url": "http://cat.example/tree",
            "category_update_time_interval": 123,
        }
        legacy_cfg.update(legacy_overrides or {})
        legacy_cfg_path.write_text(json.dumps(legacy_cfg), encoding="utf-8")
    cfg = {
        "engine_config_path": "/dev/null",
        "embedding_config_path": "/dev/null",
        **({"legacy_search_config_path": str(legacy_cfg_path)} if with_legacy else {}),
        **cfg_extra,
    }
    cfg_path = tmp_path / "config_test.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return str(cfg_path)


def test_from_config_loads_legacy_business_settings(patched_service, tmp_path, caplog):
    path = _write_cfg(tmp_path, test_index_name="test_case")
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path, index_name="prod_idx")
    assert svc._multimodal_prefix == "https://file.example.com/"
    assert svc._check_duplicate is False
    assert svc._is_need_llm is True
    assert svc._category.service_url == "http://cat.example/tree"
    assert svc._category.update_interval == 123
    assert svc._default_index == "prod_idx"
    # 显式 index + prefix 配置齐全 → 不应有任何 warning
    assert [r for r in caplog.records if "multimodal_prefix" in r.message] == []
    assert [r for r in caplog.records if "索引" in r.message] == []


def test_from_config_missing_legacy_cfg_warns_and_defaults(patched_service, tmp_path, caplog):
    path = _write_cfg(tmp_path, with_legacy=False, test_index_name="test_case")
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path, index_name="prod_idx")
    assert svc._multimodal_prefix == ""
    assert svc._check_duplicate is True   # 内置缺省与旧 config.get('check_duplicate', True) 一致
    assert svc._is_need_llm is False
    msgs = " | ".join(r.message for r in caplog.records)
    assert "legacy_search_config_path" in msgs
    assert "multimodal_prefix" in msgs  # 占位符将被删除的醒目告警


def test_from_config_empty_prefix_in_legacy_cfg_warns(patched_service, tmp_path, caplog):
    path = _write_cfg(tmp_path, legacy_overrides={"multimodal_prefix": ""},
                      test_index_name="test_case")
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path, index_name="prod_idx")
    assert svc._multimodal_prefix == ""
    assert any("multimodal_prefix" in r.message for r in caplog.records)


def test_from_config_index_resolution_order(patched_service, tmp_path, caplog):
    # default_index_name 优先于 test_index_name，且不告警
    path = _write_cfg(tmp_path, default_index_name="prod_idx", test_index_name="test_case")
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path)
    assert svc._default_index == "prod_idx"
    assert [r for r in caplog.records if "test_index_name" in r.message] == []

    # 只有 test_index_name → 使用但**告警**（不再静默误用测试索引）
    caplog.clear()
    path = _write_cfg(tmp_path, test_index_name="test_case")
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path)
    assert svc._default_index == "test_case"
    assert any("test_index_name" in r.message for r in caplog.records)

    # 两者皆无 → 回退 engine config 索引，告警
    caplog.clear()
    path = _write_cfg(tmp_path)
    with caplog.at_level(logging.WARNING, logger="kdb.crud.service"):
        svc = patched_service.KnowledgeService.from_config(path)
    assert svc._default_index == "engine_default_idx"
    assert any("回退 engine config" in r.message for r in caplog.records)
