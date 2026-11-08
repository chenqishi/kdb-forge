from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
撤回一批文档挖掘任务灌进 ES 的知识（软删，不物理删除）。

用途：`build_doc_mining_tasks.py --submit` 投递后，若发现灌进去的知识不合适，
按 `task_id` 批量软删（`del_flag=1` + `flag=<批次标记>`），并复核 active 归零。

**为什么必须先有这个脚本再灌库**：灌库是写生产库、知识会进入线上检索，
没有撤回手段就等于不可逆。本脚本在投递前就写好并演练 dry-run。

⚠️ 两个已实测的坑（见 MEMORY 2026-08-08 Wayfair 软删那条）：
1. 阿里云 ES Serverless 带大向量文档时，`update_by_query` 的 `scroll_size` 稍大
   （如 100）会触发 `MAX_WRITE_SIZE_PER_REQUEST`，**而且可能已提交了部分数据**——
   所以默认用小批次（10），且**必须检查响应体里的 `error`**，不能只看 HTTP 200。
2. 软删后要**复核 active 数归零**，不能假设成功。

默认 dry-run，只统计不写入；加 `--apply` 才真正软删。
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict
from typing import List
from typing import Optional

PROJECT_ROOT = str(_PROJECT_ROOT)

LOGGER = logging.getLogger(__name__)


def _client(config_path: str):
    from kdb.shared.clients.es_http_client import EsHttpClient
    return EsHttpClient.from_config(config_path)


def build_query(task_ids: List[str], from_file_names: Optional[List[str]] = None,
                only_active: bool = True) -> Dict:
    """按 task_id（优先）或 from_file_name 定位本批灌入的知识。"""
    should = []
    if task_ids:
        should.append({'terms': {'task_id.keyword': task_ids}})
    if from_file_names:
        should.append({'terms': {'ext_info.from_file_name.keyword': from_file_names}})
    if not should:
        raise ValueError('必须给 task_ids 或 from_file_names 之一')

    must = [{'bool': {'should': should, 'minimum_should_match': 1}}]
    if only_active:
        must.append({'term': {'del_flag': 0}})
    return {'bool': {'must': must}}


def count(es, index: str, query: Dict) -> int:
    return es.count(index, query)


def soft_delete(es, index: str, query: Dict, flag: str,
                batch_size: int = 10) -> Dict:
    """小批次软删。逐批检查响应 error，不吞错。"""
    url = f"{es.base_url}/{index}/_update_by_query"
    params = {'conflicts': 'proceed', 'scroll_size': batch_size,
              'wait_for_completion': 'true', 'refresh': 'true'}
    body = {
        'query': query,
        'script': {
            'source': "ctx._source.del_flag = 1; ctx._source.flag = params.flag;",
            'lang': 'painless',
            'params': {'flag': flag},
        },
    }
    # 复用 EsHttpClient 自己的 session/auth，避免重复拼凭证
    resp = es.session.post(url, params=params, json=body,
                           auth=es.auth, timeout=es.timeout)
    data = resp.json()
    # 关键：HTTP 200 不代表成功，必须看响应体的 failures/error
    failures = data.get('failures') or []
    if failures or data.get('error'):
        raise RuntimeError('软删失败（可能已部分提交）：%s' %
                           json.dumps(data, ensure_ascii=False)[:500])
    return data


def main():
    ap = argparse.ArgumentParser(description='撤回文档挖掘任务灌入的知识（软删）')
    ap.add_argument('--index', required=True, help='ES 索引名，如 payoneer_olive')
    ap.add_argument('--task-ids', default='', help='逗号分隔的 task_id')
    ap.add_argument('--task-ids-file', default=None,
                    help='投递时保存的 submitted_tasks.json，自动取其中的 task_id')
    ap.add_argument('--flag', required=True, help='批次标记，如 rollback_20260829')
    ap.add_argument('--es-config', default=os.path.join(PROJECT_ROOT, 'config', 'config_es_engine.json'))
    ap.add_argument('--batch-size', type=int, default=10,
                    help='scroll_size；Serverless 上别调大，会 MAX_WRITE_SIZE_PER_REQUEST')
    ap.add_argument('--apply', action='store_true', help='真正执行软删（默认只统计）')
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    task_ids = [t.strip() for t in args.task_ids.split(',') if t.strip()]
    if args.task_ids_file and os.path.exists(args.task_ids_file):
        with open(args.task_ids_file, 'r', encoding='utf-8') as f:
            recs = json.load(f)
        for r in recs if isinstance(recs, list) else []:
            tid = r.get('task_id') if isinstance(r, dict) else None
            if tid and tid not in task_ids:
                task_ids.append(tid)
    if not task_ids:
        raise SystemExit('没有拿到任何 task_id')

    es = _client(args.es_config)
    q = build_query(task_ids)
    n = count(es, args.index, q)
    print(f'索引 {args.index} 中属于这 {len(task_ids)} 个任务的 active 知识：{n} 条')

    if not args.apply:
        print('未加 --apply，只做统计，未写入任何数据。')
        return
    if n == 0:
        print('没有需要软删的条目。')
        return

    res = soft_delete(es, args.index, q, args.flag, batch_size=args.batch_size)
    print(f"软删完成：updated={res.get('updated')} / total={res.get('total')}")

    # 复核：必须归零，不能假设成功
    left = count(es, args.index, q)
    print(f'复核剩余 active：{left}')
    if left:
        raise SystemExit(f'⚠️ 仍有 {left} 条未软删，请用更小的 batch-size 重跑')


if __name__ == '__main__':
    main()
