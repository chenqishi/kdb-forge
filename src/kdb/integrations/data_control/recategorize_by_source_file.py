#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
按来源文件名把整批知识改挂到指定类目。

场景：文档挖掘任务投递时 `category_id` 填错了（比如一个任务里混投了两个平台的 PDF，
整批知识跟着任务级的 category 挂到了同一个组），导致某个文件的知识全部分错组。
这种错误 title 里没有任何信号，`assign_platform_category` 那套「从 title 猜平台」
的逻辑救不了，只能由人指定「哪个文件 → 哪个类目」。

写回的 `category_infos` + `primary_category` 结构直接复用 `assign_platform_category`，
两边保持一致；同样是默认 dry-run，`--execute` 才写，写前落 rollback.jsonl。

用法：

    # 1) dry-run，先看圈到了哪些、原来挂在哪
    python3 data_control_tools/recategorize_by_source_file.py \\
        --index payoneer_olive_payoneer_olive --client payoneer_olive \\
        --category "Mercado Libre" \\
        --file-name "美客多全站点 入驻资料提交指南.pdf" \\
        --work-dir output/recategorize_20260821

    # 2) 写回
    ... --execute

    # 3) 回滚
    ... --rollback output/recategorize_20260821/rollback.jsonl --execute
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/recategorize_by_source_file.py')

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from category_sys_manager.category_sys_util import (  # noqa: E402
    build_category_path_map, get_category_tree)
from data_control_tools.assign_platform_category import (  # noqa: E402
    apply_updates, build_category_fields, run_rollback)
from data_control_tools.relabel_qa_quality_by_llm import (  # noqa: E402
    DEFAULT_BULK_BATCH, DEFAULT_ES_CONFIG, EsHttpClient, _write_jsonl)


def build_target_query(file_names: List[str], task_ids: Optional[List[str]] = None,
                       include_deleted: bool = False) -> Dict[str, Any]:
    """
    按来源文件名（+ 可选任务 id）圈定待改组知识。

    `ext_info.from_file_name` 是 text，必须走 `.keyword` 精确匹配；
    `task_id` 本身就是 keyword，**没有** `.keyword` 子字段。
    """
    filters: List[Dict[str, Any]] = [
        {'terms': {'ext_info.from_file_name.keyword': file_names}}]
    if task_ids:
        filters.append({'terms': {'task_id': task_ids}})
    if not include_deleted:
        filters.append({'term': {'del_flag': 0}})
    return {'bool': {'filter': filters}}


def download_targets(es: EsHttpClient, index: str, query: Dict[str, Any],
                     page_size: int = 1000) -> List[Dict[str, Any]]:
    """拉待改组文档的现有类目字段（不落缓存：圈定的量都很小，且要看到最新状态）"""
    fields = ['title', 'data_type', 'task_id', 'ext_info.from_file_name',
              'category_infos', 'primary_category']
    docs = []
    for did, src in es.iter_search_after(index, query, fields, page_size=page_size):
        docs.append({
            '_id': did,
            'title': src.get('title') or '',
            'data_type': src.get('data_type'),
            'task_id': src.get('task_id'),
            'from_file_name': (src.get('ext_info') or {}).get('from_file_name') or '',
            'old_category': (src.get('primary_category') or {}).get('category_path') or '',
            'old_category_infos': src.get('category_infos'),
            'old_primary_category': src.get('primary_category'),
        })
    logging.info('圈定 %d 条 ← %s', len(docs), index)
    return docs


def plan_recategorize(docs: List[Dict[str, Any]], category_name: str,
                      category_id: str) -> List[Dict[str, Any]]:
    """目标类目是人指定的唯一值，只有当前类目不同的才需要写回"""
    plans = []
    for doc in docs:
        plan = dict(doc)
        plan['new_category'] = category_name
        plan['category_id'] = category_id
        plan['changed'] = doc.get('old_category') != category_name
        plans.append(plan)
    return plans


def build_report(plans: List[Dict[str, Any]], sample_size: int = 5) -> Dict[str, Any]:
    """按「文件名 × 原类目」分布 + 抽样，人工核对用"""
    dist: Dict[str, Dict[str, int]] = {}
    for p in plans:
        old = p.get('old_category') or '(无 primary_category)'
        dist.setdefault(p['from_file_name'], {}).setdefault(old, 0)
        dist[p['from_file_name']][old] += 1
    changed = [p for p in plans if p['changed']]
    return {
        'total': len(plans),
        'changed': len(changed),
        'unchanged': len(plans) - len(changed),
        'by_file_and_old_category': dist,
        'samples': [{'title': p['title'], 'data_type': p['data_type'],
                     'from': p.get('old_category') or '(无)', 'to': p['new_category']}
                    for p in changed[:sample_size]],
    }


def load_category_id(client: str, category_path: str) -> str:
    """从线上类目树取 id；不存在就报错，绝不硬编码或新建"""
    if '-' in category_path:
        # 复用的 build_category_fields 只写 cate1_*，二级类目会丢掉层级信息，先挡住
        raise SystemExit('暂只支持一级类目，收到二级路径：%s' % category_path)
    path_map = build_category_path_map(get_category_tree(client))
    if category_path not in path_map:
        raise SystemExit(
            '类目不存在：%s（client=%s）。现有类目示例：%s'
            % (category_path, client, list(path_map)[:10]))
    return str(path_map[category_path])


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='按来源文件名把整批知识改挂到指定类目')
    p.add_argument('--es-config', default=DEFAULT_ES_CONFIG)
    p.add_argument('--index', required=True, help='ES 索引名，如 payoneer_olive_payoneer_olive')
    p.add_argument('--client', required=True, help='类目树所属 client，如 payoneer_olive')
    p.add_argument('--category', default='', help='目标类目完整路径，二级用 - 连接')
    p.add_argument('--file-name', action='append', default=[],
                   help='来源文件名精确值，可重复')
    p.add_argument('--task-id', action='append', default=[],
                   help='叠加任务过滤，可重复')
    p.add_argument('--work-dir', default='')
    p.add_argument('--include-deleted', action='store_true',
                   help='连 del_flag=1 的软删知识一起改')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--rollback', default='')
    p.add_argument('--bulk-batch', type=int, default=DEFAULT_BULK_BATCH)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    args = build_arg_parser().parse_args(argv)
    es = EsHttpClient.from_config(args.es_config)

    if args.rollback:
        if not args.execute:
            print('--rollback 需要配合 --execute')
            return 1
        print(json.dumps(run_rollback(es, args.index, args.rollback, args.bulk_batch),
                         ensure_ascii=False, indent=2))
        return 0

    if not args.file_name:
        print('--file-name 必填（可重复）')
        return 1
    if not args.category:
        print('--category 必填')
        return 1

    category_id = load_category_id(args.client, args.category)
    logging.info('目标类目 %s -> %s', args.category, category_id)

    work_dir = args.work_dir or os.path.join(PROJECT_ROOT, 'output',
                                             'recategorize_%s' % args.index)
    os.makedirs(work_dir, exist_ok=True)

    query = build_target_query(args.file_name, args.task_id, args.include_deleted)
    docs = download_targets(es, args.index, query)
    plans = plan_recategorize(docs, args.category, category_id)
    _write_jsonl(os.path.join(work_dir, 'plans.jsonl'), plans)

    report = build_report(plans)
    report['index'] = args.index
    report['target_category'] = {'path': args.category, 'id': category_id}
    if not args.execute:
        report['mode'] = 'dry-run（加 --execute 才写）'
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    result = apply_updates(es, args.index, plans,
                           os.path.join(work_dir, 'rollback.jsonl'), args.bulk_batch)
    report['mode'] = 'execute'
    report['result'] = result
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not result.get('failed') else 1


if __name__ == '__main__':
    sys.exit(main())
