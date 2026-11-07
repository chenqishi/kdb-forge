#!/usr/bin/env python
# -*- coding:utf8 -*-

"""按快照名单软删「已被新一轮重建取代」的旧知识。

用于「先插新的、再删旧的」这种零空窗替换：插入新一轮产物之前，先把该批旧知识的
`_id` 快照下来；新数据插完、审核通过之后，再按这份快照把旧的软删掉。

为什么必须用「插入前的 _id 快照」而不是按时间/条件现场圈选：

1. 新旧两批 `task_id`、`from_type`、`from_file_name` 全一样，事后无法用业务字段区分；
2. `insert_data` 对内容完全相同的条目是 **同 _id 覆盖写**，快照里会有一部分 `_id`
   已经被新数据占用（`insert_time` 变成本轮）。这类必须排除，否则会把刚插进去的新知识删掉。
   本脚本用 `--new_since` 做这道保护。

软删口径沿用 data_control_tools/filter_ad_knowledge_by_llm.apply_deletions：
`del_flag=1` + `flag=<批次>`，写回前先落 rollback.jsonl；已经是 `del_flag=1` 的不动
（它们带着别的批次的 flag，重打标会抹掉来源）。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/retire_superseded_knowledge.py')

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

from commons.es_http_client import DEFAULT_BULK_BATCH, EsHttpClient

logging.basicConfig(level=logging.INFO,
                    format='[%(levelname)s] [%(asctime)s] %(message)s')


def load_snapshot_ids(snapshot_file: str) -> List[str]:
    """读取插入前落的快照，返回去重排序后的 _id 列表。

    快照可以是 JSON 数组（元素含 `_id`）或每行一个 _id 的纯文本。
    """
    with open(snapshot_file, 'r', encoding='utf-8') as f:
        head = f.read(1)
        f.seek(0)
        if head == '[':
            rows = json.load(f)
            ids = [r['_id'] if isinstance(r, dict) else str(r) for r in rows]
        else:
            ids = [l.strip() for l in f if l.strip()]
    return sorted(set(ids))


def fetch_current_state(es: EsHttpClient, index: str, ids: List[str],
                        chunk: int = 500) -> Dict[str, Dict[str, Any]]:
    """按 _id 批量取回当前的 del_flag / flag / insert_time。

    用 `ids` query 而不是逐条 GET：几千条时逐条 GET 会打满连接。
    """
    state: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(ids), chunk):
        batch = ids[start:start + chunk]
        for doc_id, src in es.iter_search_after(
                index, {'ids': {'values': batch}},
                ['del_flag', 'flag', 'insert_time', 'quality_level', 'audit_result'],
                page_size=chunk):
            state[doc_id] = src
    return state


def plan_retire(state: Dict[str, Dict[str, Any]], snapshot_ids: List[str],
                new_since: Optional[str]) -> Tuple[List[str], Dict[str, List[str]]]:
    """把快照名单分成「该删」和各类「跳过」。

    跳过三类：
      - missing:      快照后文档已不在索引里
      - already_del:  已经是 del_flag=1，带着别的批次的 flag，不重打标
      - overwritten:  insert_time >= new_since，说明这个 _id 已被本轮新数据覆盖写
    """
    to_delete: List[str] = []
    skipped: Dict[str, List[str]] = {'missing': [], 'already_del': [], 'overwritten': []}
    for doc_id in snapshot_ids:
        src = state.get(doc_id)
        if src is None:
            skipped['missing'].append(doc_id)
            continue
        if src.get('del_flag'):
            skipped['already_del'].append(doc_id)
            continue
        if new_since and (src.get('insert_time') or '') >= new_since:
            skipped['overwritten'].append(doc_id)
            continue
        to_delete.append(doc_id)
    return to_delete, skipped


def retire(config_path: str, index: str, snapshot_file: str, flag_value: str,
           work_dir: str, new_since: Optional[str] = None,
           bulk_batch: int = DEFAULT_BULK_BATCH, execute: bool = False) -> Dict[str, Any]:
    """主流程：读快照 → 取现状 → 分类 → 落 rollback → 软删。默认 dry-run。"""
    es = EsHttpClient.from_config(config_path)
    snapshot_ids = load_snapshot_ids(snapshot_file)
    logging.info('快照 _id 数: %d', len(snapshot_ids))

    state = fetch_current_state(es, index, snapshot_ids)
    to_delete, skipped = plan_retire(state, snapshot_ids, new_since)
    logging.info('待软删 %d | 跳过: 已删 %d / 被新数据覆盖 %d / 索引里已不存在 %d',
                 len(to_delete), len(skipped['already_del']),
                 len(skipped['overwritten']), len(skipped['missing']))

    os.makedirs(work_dir, exist_ok=True)
    rollback_file = os.path.join(work_dir, 'rollback.jsonl')
    with open(rollback_file, 'w', encoding='utf-8') as f:
        for doc_id in to_delete:
            src = state[doc_id]
            f.write(json.dumps({'_id': doc_id, 'del_flag': src.get('del_flag'),
                                'flag': src.get('flag')}, ensure_ascii=False) + '\n')
    logging.info('回滚文件已写: %s', rollback_file)

    result: Dict[str, Any] = {'planned': len(to_delete), 'rollback_file': rollback_file,
                              'skipped': {k: len(v) for k, v in skipped.items()}}
    if not execute:
        logging.info('[dry-run] 未写回，加 --execute 才真正软删')
        result['dry_run'] = True
        return result

    updates = [(doc_id, {'del_flag': 1, 'flag': flag_value}) for doc_id in to_delete]
    bulk = es.bulk_update_doc(index, updates, batch_size=bulk_batch)
    result['updated'] = bulk.get('updated', 0)
    result['failed'] = bulk.get('failed', [])
    logging.info('软删完成 updated=%d failed=%d', result['updated'], len(result['failed']))
    return result


def rollback(config_path: str, index: str, rollback_file: str,
             bulk_batch: int = DEFAULT_BULK_BATCH, execute: bool = False) -> Dict[str, Any]:
    """按 rollback.jsonl 把 del_flag / flag 写回原值。"""
    es = EsHttpClient.from_config(config_path)
    updates: List[Tuple[str, Dict[str, Any]]] = []
    for line in open(rollback_file, 'r', encoding='utf-8'):
        if not line.strip():
            continue
        item = json.loads(line)
        doc = {'del_flag': item.get('del_flag') if item.get('del_flag') is not None else 0}
        if item.get('flag') is not None:
            doc['flag'] = item['flag']
        updates.append((item['_id'], doc))
    if not execute:
        logging.info('[dry-run] 将回滚 %d 条', len(updates))
        return {'planned': len(updates), 'dry_run': True}
    return es.bulk_update_doc(index, updates, batch_size=bulk_batch)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('run', help='按快照软删旧知识')
    p.add_argument('--config', default='config/config_es_engine.json')
    p.add_argument('--index', required=True)
    p.add_argument('--snapshot_file', required=True, help='插入新数据之前落的 _id 快照')
    p.add_argument('--flag', required=True, help='批次标记，形如 qa_regen_wayfair_20260903')
    p.add_argument('--work_dir', required=True, help='rollback.jsonl 落盘目录')
    p.add_argument('--new_since', default=None,
                   help='本轮新数据的最早 insert_time，形如 "2026-09-03 00:00:00"；'
                        'insert_time >= 该值的文档视为已被新数据覆盖写，不删')
    p.add_argument('--bulk_batch', type=int, default=DEFAULT_BULK_BATCH)
    p.add_argument('--execute', action='store_true')

    r = sub.add_parser('rollback', help='按 rollback.jsonl 撤销软删')
    r.add_argument('--config', default='config/config_es_engine.json')
    r.add_argument('--index', required=True)
    r.add_argument('--rollback_file', required=True)
    r.add_argument('--bulk_batch', type=int, default=DEFAULT_BULK_BATCH)
    r.add_argument('--execute', action='store_true')

    args = parser.parse_args()
    if args.cmd == 'run':
        out = retire(args.config, args.index, args.snapshot_file, args.flag,
                     args.work_dir, args.new_since, args.bulk_batch, args.execute)
    else:
        out = rollback(args.config, args.index, args.rollback_file,
                       args.bulk_batch, args.execute)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
