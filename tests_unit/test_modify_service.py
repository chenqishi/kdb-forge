#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""kdb.modify.apply_modify_plan 单测（mock KnowledgeService，不碰真实 ES）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from kdb.modify import ModifyPlan, UpdateItem, InsertItem, apply_modify_plan


class FakeService:
    """记录调用、可控成败的假 KnowledgeService。"""

    def __init__(self, update_ok=True, insert_ok=True):
        self.update_calls = []
        self.insert_calls = []
        self._update_ok = update_ok
        self._insert_ok = insert_ok

    def update(self, data_id, doc, index_name=None, regenerate_embedding=False, refresh=False):
        self.update_calls.append({"data_id": data_id, "doc": doc, "index_name": index_name,
                                  "regen": regenerate_embedding, "refresh": refresh})
        return self._update_ok

    def insert_text(self, doc, index_name=None, refresh_imm=False):
        self.insert_calls.append({"doc": doc, "index_name": index_name})
        return (self._insert_ok, "" if self._insert_ok else "insert failed")


def test_update_applies_by_id_with_regen_and_single_index():
    svc = FakeService()
    plan = ModifyPlan(es_index="mercado_admin@x", updates=[
        UpdateItem(document_id="d1", new_content="新答案A", new_title="问题A", old_content="旧A"),
    ])
    r = apply_modify_plan(svc, plan, dry_run=False)
    assert r.success and r.has_correction
    assert len(svc.update_calls) == 1
    c = svc.update_calls[0]
    assert c["data_id"] == "d1" and c["index_name"] == "mercado_admin@x"
    assert c["doc"] == {"content": "新答案A", "title": "问题A"}
    assert c["regen"] is True and c["refresh"] is True   # 改内容必须重算向量
    assert r.updated_items[0]["applied"] is True


def test_insert_only_when_allow_insert():
    svc = FakeService()
    # allow_insert=False → 不插
    plan = ModifyPlan(es_index="idx", insert=InsertItem(title="新Q", content="新A"), allow_insert=False)
    r = apply_modify_plan(svc, plan, dry_run=False)
    assert svc.insert_calls == []
    assert r.inserted_item is None
    # allow_insert=True → 插
    svc2 = FakeService()
    plan2 = ModifyPlan(es_index="idx", insert=InsertItem(title="新Q", content="新A"), allow_insert=True)
    r2 = apply_modify_plan(svc2, plan2, dry_run=False)
    assert len(svc2.insert_calls) == 1
    assert svc2.insert_calls[0]["index_name"] == "idx"
    assert r2.inserted_item["applied"] is True


def test_dry_run_does_not_write():
    svc = FakeService()
    plan = ModifyPlan(es_index="idx", updates=[UpdateItem(document_id="d1", new_content="x")],
                      insert=InsertItem(title="q", content="a"), allow_insert=True)
    r = apply_modify_plan(svc, plan, dry_run=True)
    assert svc.update_calls == [] and svc.insert_calls == []  # 没有任何真写
    assert r.dry_run is True and r.success is True
    assert r.updated_items[0]["applied"] is False


def test_empty_es_index_rejected():
    svc = FakeService()
    r = apply_modify_plan(svc, ModifyPlan(es_index="", updates=[UpdateItem("d1", "x")]), dry_run=False)
    assert r.success is False and "empty_es_index" in r.errors
    assert svc.update_calls == []


def test_single_index_all_writes_same_index():
    svc = FakeService()
    plan = ModifyPlan(es_index="only_idx",
                      updates=[UpdateItem("d1", "a"), UpdateItem("d2", "b")],
                      insert=InsertItem(title="q", content="c"), allow_insert=True)
    apply_modify_plan(svc, plan, dry_run=False)
    idxs = {c["index_name"] for c in svc.update_calls} | {c["index_name"] for c in svc.insert_calls}
    assert idxs == {"only_idx"}   # 全部打到同一个 index


def test_update_failure_recorded_in_errors():
    svc = FakeService(update_ok=False)
    r = apply_modify_plan(svc, ModifyPlan(es_index="i", updates=[UpdateItem("d1", "x")]), dry_run=False)
    assert r.updated_items[0]["applied"] is False
    assert any("update_failed" in e for e in r.errors)
    assert r.success is False
