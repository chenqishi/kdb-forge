#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kdb.api FastAPI 层单测（TestClient）。

只验证薄路由的接线：
- dry_run=True 必须**不**构建真实 KnowledgeService（不碰 ES），仍返回 ModifyResult。
- pydantic 请求体正确映射到 ModifyPlan.from_dict（含 updates/insert/allow_insert）。
- 非法 payload（缺必填 es_index）被 FastAPI 校验拒绝（422）。

API 模块懒加载 CRUD。导入错误应使测试失败，不再以缺旧依赖为由跳过。
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from fastapi.testclient import TestClient  # noqa: E402
import kdb.api.knowledge_routes as kr  # noqa: E402
from kdb.api.app import app  # noqa: E402


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
