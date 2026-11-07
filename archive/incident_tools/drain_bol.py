#!/usr/bin/env python
# -*- coding:utf8 -*-
"""持续 stop_task + 软删，直到队列排空且 active 归零。

背景：328 个文档挖掘任务被误投到线上任务服务（应在本机跑）。服务端队列是内存 Queue，
**没有取消排队任务的接口**，worker 取出任务时也不检查是否已被 stop
（`off_task_control_service.py:136-176` 直接 `start_mining_task`），
所以排队中的任务必然会执行。唯一可行的办法是持续跟进：
任务一转"运行中"就 stop，写进去的知识就软删，直到队列排空。
"""
import collections
import json
import logging
import sys
import time

import requests

sys.path.insert(0, '/root/knowledge_database_builder')
logging.basicConfig(level=logging.ERROR)

from data_control_tools.rollback_mining_tasks import build_query, count, soft_delete, _client

BASE = 'http://120.77.147.247:6000'
WORK = '/root/knowledge_database_builder/data/payoneer_olive/Bol_ingest_rel/_work'
FLAG = 'rollback_bol_20260829'

recs = json.load(open(f'{WORK}/submitted_tasks.json', encoding='utf-8'))
ids = [r['task_id'] for r in recs]
es = _client('/root/knowledge_database_builder/config/config_es_engine.json')


def states():
    """run_status: 4=排队中 2=运行中 3=运行完成 1=手动停止/异常"""
    c = collections.Counter()
    for t in ids:
        try:
            d = requests.post(f'{BASE}/task_info', json={'task_id': t}, timeout=10).json()
            c[str((d.get('data') or {}).get('run_status'))] += 1
        except Exception:
            c['EXC'] += 1
    return c


def active_count():
    n = 0
    for i in range(0, len(ids), 100):
        n += count(es, 'payoneer_olive', build_query(ids[i:i + 100], only_active=True))
    return n


def main():
    for rnd in range(1, 300):
        stopped = 0
        for t in ids:
            try:
                if requests.post(f'{BASE}/stop_task', json={'task_id': t},
                                 timeout=10).json().get('code') == 0:
                    stopped += 1
            except Exception:
                pass

        for i in range(0, len(ids), 100):
            q = build_query(ids[i:i + 100], only_active=True)
            if count(es, 'payoneer_olive', q):
                try:
                    soft_delete(es, 'payoneer_olive', q, FLAG, batch_size=5)
                except Exception as exc:
                    print('  软删告警:', str(exc)[:70], flush=True)

        st = states()
        act = active_count()
        pending = st.get('4', 0) + st.get('2', 0)
        print('轮%3d | stop %2d | 排队%3d 运行%2d 完成%3d 停止%3d | active %d'
              % (rnd, stopped, st.get('4', 0), st.get('2', 0),
                 st.get('3', 0), st.get('1', 0), act), flush=True)
        if pending == 0 and act == 0:
            print('✅ 队列已排空、active 归零')
            return
        time.sleep(45)


if __name__ == '__main__':
    main()
