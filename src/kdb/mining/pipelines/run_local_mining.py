#!/usr/bin/env python
# -*- coding:utf8 -*-
"""本机批量运行文档挖掘，直接调用当前项目控制器。

使用当前 Python 环境；KDB_PYTHON 可指定已配置依赖的其他解释器。
子进程继承当前环境，并通过 PYTHONPATH 加入当前项目 src。
产出 local_mining_tasks.json，逐篇记录 task_id 与退出码，供撤回使用。
"""
import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from kdb.shared.config.paths import PROJECT_ROOT, subprocess_env

MINING_PYTHON = os.environ.get('KDB_PYTHON') or sys.executable
ENTRY_MODULE = 'kdb.mining.pipelines.document_qa_segment'


def make_env():
    return subprocess_env()


def gen_task_id(task_type, task_info):
    """与线上一致：md5(task_type + task_info + 时间戳)，含时间戳所以不可预先推算。"""
    return hashlib.md5((task_type + task_info + str(time.time())).encode()).hexdigest()


def run_one(item, log_dir, env):
    name, task_type, task_info = item
    task_id = gen_task_id(task_type, task_info)
    log_path = os.path.join(log_dir, f'{task_id[:12]}.log')
    cmd = [MINING_PYTHON, '-u', '-m', ENTRY_MODULE, '--script-dir', str(PROJECT_ROOT),
           '--task-id', task_id, '--task-info', task_info]
    t0 = time.time()
    with open(log_path, 'w', encoding='utf-8') as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                            cwd=PROJECT_ROOT, env=env).returncode
    return {'name': name, 'task_id': task_id, 'rc': rc,
            'secs': round(time.time() - t0, 1), 'log': log_path}


def main():
    ap = argparse.ArgumentParser(description='本机批量文档挖掘')
    ap.add_argument('--tasks-file', required=True, help='build_doc_mining_tasks 产出的 tasks.json')
    ap.add_argument('--out', default=None, help='task_id 记录文件（撤回用）')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--skip', default='', help='逗号分隔的文件名，跳过已跑过的')
    ap.add_argument('--skip-from', default=None,
                    help='已跑记录 json（如 local_mining_tasks.json），自动跳过其中 rc==0 的篇目。'
                         '比手工传 --skip 可靠：主批边跑边覆写该文件，'
                         '若在主批结束前取快照会漏掉后完成的篇目，导致重复灌库')
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    payloads = json.load(open(args.tasks_file, encoding='utf-8'))
    skip = {s.strip() for s in args.skip.split(',') if s.strip()}
    # 从记录文件读已成功篇目：必须在主批**结束后**读，否则快照不全
    if args.skip_from and os.path.exists(args.skip_from):
        with open(args.skip_from, 'r', encoding='utf-8') as f:
            for rec in json.load(f):
                if isinstance(rec, dict) and rec.get('rc') == 0 and rec.get('name'):
                    skip.add(rec['name'])
    items = []
    for p in payloads:
        ti = p['task_info'] if isinstance(p['task_info'], str) \
            else json.dumps(p['task_info'], ensure_ascii=False)
        name = json.loads(ti)['files'][0]['name']
        if name in skip:
            continue
        items.append((name, p['task_type'], ti))
    if args.limit:
        items = items[:args.limit]

    log_dir = os.path.join(os.path.dirname(args.tasks_file), 'mine_logs')
    os.makedirs(log_dir, exist_ok=True)
    out_path = args.out or os.path.join(os.path.dirname(args.tasks_file),
                                        'local_mining_tasks.json')

    env = make_env()
    print(f'待跑 {len(items)} 篇，并发 {args.workers}，日志 {log_dir}', flush=True)

    done, ok, fail = [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, r in enumerate(pool.map(lambda it: run_one(it, log_dir, env), items), 1):
            done.append(r)
            if r['rc'] == 0:
                ok += 1
            else:
                fail += 1
                print(f"  ✗ {r['name'][:50]} rc={r['rc']} 见 {r['log']}", flush=True)
            # 每篇都落盘 task_id，中途被杀也能撤回
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(done, f, ensure_ascii=False, indent=1)
            if i % 10 == 0 or i == len(items):
                print(f'  进度 {i}/{len(items)} | 成功 {ok} 失败 {fail}', flush=True)

    print(f'完成：成功 {ok} / 失败 {fail}，task_id 记录 → {out_path}')


if __name__ == '__main__':
    main()
