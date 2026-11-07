from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding: utf-8 -*-
"""`supply_missing_field.build_missing_field_query` 的选取范围。

回归背景：原来写成 `must_not: [exists f1, exists f2]`，语义是「既没有 f1 也没有 f2」，
一次传 `dataset,primary_category` 只会捞到两个字段都缺的文档。
实测 payoneer_olive 缺 dataset 2629 条、缺 primary_category 74 条（后者是前者子集），
按旧逻辑只更新 74 条，另外 2555 条被静默跳过，日志还显示「处理完成」。
"""
import os
import sys

import pytest


supply = pytest.importorskip('kdb.retrieval.maintenance.supply_missing_field',
                             reason='依赖 elasticsearch 客户端，环境缺时跳过')


def _matches(query, doc):
    """按 bool 语义在本地判定一条文档是否会被查询选中（只支持这里用到的子集）。"""
    b = query['bool']
    for cond in b.get('must', []):
        field, value = list(cond['term'].items())[0]
        if doc.get(field) != value:
            return False
    shoulds = b.get('should')
    if not shoulds:
        return True
    hit = 0
    for clause in shoulds:
        field = clause['bool']['must_not']['exists']['field']
        if field not in doc:
            hit += 1
    return hit >= b.get('minimum_should_match', 1)


ALIVE = {'del_flag': 0}


def test_picks_doc_missing_only_one_of_the_fields():
    """只缺 dataset 的必须被选中——这是漏掉 2555 条的直接原因。"""
    q = supply.build_missing_field_query(['dataset', 'primary_category'])
    doc = dict(ALIVE, primary_category={'category_path': '默认分组'})
    assert _matches(q, doc)


def test_picks_doc_missing_both_fields():
    q = supply.build_missing_field_query(['dataset', 'primary_category'])
    assert _matches(q, dict(ALIVE))


def test_skips_doc_that_has_every_field():
    q = supply.build_missing_field_query(['dataset', 'primary_category'])
    doc = dict(ALIVE, dataset='payoneer_olive', primary_category={'category_path': 'Bol'})
    assert not _matches(q, doc)


def test_skips_deleted_doc():
    q = supply.build_missing_field_query(['dataset'])
    assert not _matches(q, {'del_flag': 1})


def test_force_mode_takes_every_alive_doc():
    q = supply.build_missing_field_query(['dataset'], force=True)
    assert _matches(q, dict(ALIVE, dataset='payoneer_olive'))
    assert 'should' not in q['bool']


def test_source_excludes_drops_vectors():
    """scroll 拉全量 _source 会把两个 1024 维向量一起传下来。"""
    assert 'title_embedding' in supply.SOURCE_EXCLUDES
    assert 'content_embedding' in supply.SOURCE_EXCLUDES
