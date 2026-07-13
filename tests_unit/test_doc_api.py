#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""/knowledge/insert 与 /knowledge/delete 薄路由单测（TestClient + fake service 注入）。

只验证接线：请求体 → KnowledgeService.insert_data / delete 的参数映射、响应字段、
必填校验（422）、异常兜底（success=False 不 500）。不碰 ES/embedding——通过预置
kr._svc 为 fake，绕开 _get_service() 的真实构建。
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

for _cand in [os.environ.get("KDB_LEGACY_ROOT", ""), "/root/knowledge_database_builder"]:
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
    reason=f"无法 import kdb.api.app：{_IMPORT_ERR}",
)


class _FakeService:
    def __init__(self, insert_ret=(True, ""), delete_ret=True, raise_exc=False):
        self.insert_calls = []
        self.delete_calls = []
        self._insert_ret = insert_ret
        self._delete_ret = delete_ret
        self._raise = raise_exc

    def insert_data(self, doc, check_duplicate=None, index_name=None,
                    is_update_data=False, refresh_imm=False, **kw):
        if self._raise:
            raise RuntimeError("boom")
        self.insert_calls.append(dict(doc=doc, check_duplicate=check_duplicate,
                                      index_name=index_name, is_update_data=is_update_data,
                                      refresh_imm=refresh_imm))
        return self._insert_ret

    def delete(self, data_id, index_name=None, refresh=False):
        if self._raise:
            raise RuntimeError("boom")
        self.delete_calls.append(dict(data_id=data_id, index_name=index_name, refresh=refresh))
        return self._delete_ret


@pytest.fixture()
def client():
    kr._svc = None
    yield TestClient(app)
    kr._svc = None


def test_insert_doc_maps_params_and_keeps_synonyms_list(client):
    """doc 原样透传（synonyms_title list 不丢），参数逐一映射到 insert_data。"""
    fake = _FakeService()
    kr._svc = fake
    doc = {"_id": "kb_x1", "title": "问", "synonyms_title": ["同义1", "同义2"],
           "content": "答", "data_type": "qa", "from_type": "payoneer_demo"}
    r = client.post("/knowledge/insert", json={
        "es_index": "individual_20", "doc": doc,
        "check_duplicate": False, "is_update_data": True, "refresh_imm": True})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["document_id"] == "kb_x1"
    assert body["es_index"] == "individual_20"
    call = fake.insert_calls[0]
    assert call["doc"]["synonyms_title"] == ["同义1", "同义2"]
    assert call["check_duplicate"] is False
    assert call["index_name"] == "individual_20"
    assert call["is_update_data"] is True
    assert call["refresh_imm"] is True


def test_insert_doc_defaults(client):
    """缺省：check_duplicate=None（取服务配置缺省）/is_update_data=False/refresh_imm=False。"""
    fake = _FakeService()
    kr._svc = fake
    r = client.post("/knowledge/insert",
                    json={"es_index": "idx", "doc": {"title": "q", "content": "a"}})
    assert r.status_code == 200
    call = fake.insert_calls[0]
    assert call["check_duplicate"] is None
    assert call["is_update_data"] is False
    assert call["refresh_imm"] is False
    assert r.json()["document_id"] is None  # doc 未带 _id


def test_insert_doc_failure_and_exception(client):
    """服务返回 False → success=False 带 message；服务异常 → 兜成 success=False 不 500。"""
    kr._svc = _FakeService(insert_ret=(False, "数据重复"))
    r = client.post("/knowledge/insert", json={"es_index": "idx", "doc": {"title": "q"}})
    assert r.status_code == 200
    assert r.json() == {"success": False, "message": "数据重复",
                        "document_id": None, "es_index": "idx"}

    kr._svc = _FakeService(raise_exc=True)
    r = client.post("/knowledge/insert", json={"es_index": "idx", "doc": {"_id": "d1"}})
    assert r.status_code == 200
    assert r.json()["success"] is False
    assert "boom" in r.json()["message"]


def test_insert_doc_missing_required_422(client):
    assert client.post("/knowledge/insert", json={"doc": {"title": "q"}}).status_code == 422
    assert client.post("/knowledge/insert", json={"es_index": "idx"}).status_code == 422
    assert kr._svc is None  # 校验失败不构建服务


def test_delete_doc_maps_params(client):
    fake = _FakeService()
    kr._svc = fake
    r = client.post("/knowledge/delete", json={
        "es_index": "individual_20", "document_id": "kb_x1", "refresh": True})
    assert r.status_code == 200
    assert r.json() == {"success": True, "document_id": "kb_x1", "es_index": "individual_20"}
    assert fake.delete_calls[0] == {"data_id": "kb_x1", "index_name": "individual_20",
                                    "refresh": True}


def test_delete_doc_failure_and_validation(client):
    kr._svc = _FakeService(delete_ret=False)
    r = client.post("/knowledge/delete", json={"es_index": "idx", "document_id": "nope"})
    assert r.status_code == 200
    assert r.json()["success"] is False

    kr._svc = _FakeService(raise_exc=True)
    r = client.post("/knowledge/delete", json={"es_index": "idx", "document_id": "d"})
    assert r.status_code == 200
    assert r.json()["success"] is False

    assert client.post("/knowledge/delete", json={"es_index": "idx"}).status_code == 422
