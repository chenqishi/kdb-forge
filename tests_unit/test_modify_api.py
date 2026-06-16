#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kdb.api FastAPI 层单测（TestClient）。

只验证薄路由的接线：
- dry_run=True 必须**不**构建真实 KnowledgeService（不碰 ES），仍返回 ModifyResult。
- pydantic 请求体正确映射到 ModifyPlan.from_dict（含 updates/insert/allow_insert）。
- 非法 payload（缺必填 es_index）被 FastAPI 校验拒绝（422）。

注意：当前 kdb.api.knowledge_routes 在**模块顶层** import KnowledgeService，会经
kdb.legacy_bridge 拉入旧 ES 适配层（knowledge_interface_tools）。在没有旧依赖的纯
单测环境里这会导致 `import kdb.api.app` 直接失败（见测试报告里记录的 wiring bug）。
为了能在本机跑 API 单测，这里把 KDB_LEGACY_ROOT 指向本机旧项目副本；若不存在则 skip。
这层 import 是**生产代码缺陷**（应惰性构建），测试不修生产码，仅做标注。
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# WORKAROUND for production wiring bug: top-level KnowledgeService import drags in legacy ES.
# Point legacy root at a local copy so the module imports; skip the whole file if unavailable.
_LEGACY_CANDIDATES = [
    os.environ.get("KDB_LEGACY_ROOT", ""),
    "/root/knowledge_database_builder",
]
for _cand in _LEGACY_CANDIDATES:
    if _cand and os.path.isdir(_cand):
        os.environ["KDB_LEGACY_ROOT"] = _cand
        break

try:
    from fastapi.testclient import TestClient  # noqa: E402
    import kdb.api.knowledge_routes as kr  # noqa: E402
    from kdb.api.app import app  # noqa: E402
    _IMPORT_ERR = None
except Exception as _e:  # noqa: BLE001
    _IMPORT_ERR = _e

pytestmark = pytest.mark.skipif(
    _IMPORT_ERR is not None,
    reason=f"无法 import kdb.api.app（旧 ES 依赖缺失，生产代码顶层 import 缺陷）：{_IMPORT_ERR}",
)


@pytest.fixture()
def client():
    # 每个用例前重置共享单例，确保"dry_run 不构建服务"断言成立。
    kr._svc = None
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dry_run_does_not_build_service(client):
    """dry_run=True：返回 ModifyResult，且**不**构建真实 KnowledgeService。"""
    payload = {
        "es_index": "mercado_admin@x",
        "updates": [
            {"document_id": "d1", "new_content": "新答案", "new_title": "新问题",
             "old_content": "旧答案"},
        ],
        "insert": {"title": "新Q", "content": "新A"},
        "allow_insert": True,
        "dry_run": True,
    }
    r = client.post("/knowledge/modify_direct_update", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["success"] is True
    assert body["has_correction"] is True
    assert body["es_index"] == "mercado_admin@x"
    # 计划回显，但未真正写入
    assert body["updated_items"][0]["document_id"] == "d1"
    assert body["updated_items"][0]["applied"] is False
    assert body["updated_items"][0]["new_content"] == "新答案"
    assert body["inserted_item"]["title"] == "新Q"
    assert body["inserted_item"]["applied"] is False
    assert body["errors"] == []
    # 关键：没有构建真实服务 → 没碰 ES
    assert kr._svc is None


def test_dry_run_request_maps_to_modify_plan(client):
    """pydantic 请求体 → ModifyPlan.from_dict 映射正确（allow_insert=False 时不回显 insert）。"""
    payload = {
        "es_index": "idx",
        "updates": [{"document_id": "d9", "new_content": "x"}],
        "insert": {"title": "q", "content": "a"},
        "allow_insert": False,   # 不允许插入
        "dry_run": True,
    }
    r = client.post("/knowledge/modify_direct_update", json=payload)
    assert r.status_code == 200
    body = r.json()
    # allow_insert=False → has_correction 只看 updates，且不回显插入计划
    assert body["inserted_item"] is None
    assert body["has_correction"] is True
    assert kr._svc is None


def test_missing_es_index_rejected_by_validation(client):
    """缺必填 es_index → FastAPI 422，根本不进入业务函数。"""
    r = client.post("/knowledge/modify_direct_update",
                    json={"updates": [{"document_id": "d1", "new_content": "x"}]})
    assert r.status_code == 422
    assert kr._svc is None


def test_update_item_missing_required_field_rejected(client):
    """update 项缺 new_content（必填）→ 422。"""
    r = client.post("/knowledge/modify_direct_update",
                    json={"es_index": "idx", "updates": [{"document_id": "d1"}]})
    assert r.status_code == 422
