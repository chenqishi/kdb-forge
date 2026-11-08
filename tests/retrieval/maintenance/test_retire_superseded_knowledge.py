from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
# -*- coding:utf8 -*-

"""`plan_retire` 的分流规则。

重点是 `overwritten`：`insert_data` 对内容完全相同的条目是同 `_id` 覆盖写，
不排除就会把刚插进去的新知识当旧数据删掉。
"""

import os
import sys


from kdb.retrieval.maintenance.retire_superseded import load_snapshot_ids
from kdb.retrieval.maintenance.retire_superseded import plan_retire

NEW_SINCE = '2026-09-03 00:00:00'


def _state(**kwargs):
    base = {'del_flag': 0, 'flag': None, 'insert_time': '2026-03-27 01:00:00'}
    base.update(kwargs)
    return base


def test_普通旧数据会被删():
    state = {'a': _state()}
    to_delete, skipped = plan_retire(state, ['a'], NEW_SINCE)
    assert to_delete == ['a']
    assert all(not v for v in skipped.values())


def test_被新数据覆盖写的id不删():
    state = {'a': _state(insert_time='2026-09-03 02:37:46')}
    to_delete, skipped = plan_retire(state, ['a'], NEW_SINCE)
    assert to_delete == []
    assert skipped['overwritten'] == ['a']


def test_已软删的不重打标():
    state = {'a': _state(del_flag=1, flag='20260730')}
    to_delete, skipped = plan_retire(state, ['a'], NEW_SINCE)
    assert to_delete == []
    assert skipped['already_del'] == ['a']


def test_索引里已不存在的算missing():
    to_delete, skipped = plan_retire({}, ['a'], NEW_SINCE)
    assert to_delete == []
    assert skipped['missing'] == ['a']


def test_不传new_since时不做覆盖保护():
    state = {'a': _state(insert_time='2026-09-03 02:37:46')}
    to_delete, _ = plan_retire(state, ['a'], None)
    assert to_delete == ['a']


def test_混合场景各归各类():
    state = {
        'old': _state(),
        'new': _state(insert_time='2026-09-03 02:37:46'),
        'dead': _state(del_flag=1, flag='20260730'),
    }
    to_delete, skipped = plan_retire(state, ['dead', 'gone', 'new', 'old'], NEW_SINCE)
    assert to_delete == ['old']
    assert skipped == {'missing': ['gone'], 'already_del': ['dead'], 'overwritten': ['new']}


def test_快照两种格式都能读(tmp_path):
    j = tmp_path / 's.json'
    j.write_text('[{"_id": "b", "quality_level": "high"}, {"_id": "a"}, {"_id": "a"}]',
                 encoding='utf-8')
    assert load_snapshot_ids(str(j)) == ['a', 'b']

    t = tmp_path / 's.txt'
    t.write_text('b\na\n\na\n', encoding='utf-8')
    assert load_snapshot_ids(str(t)) == ['a', 'b']
