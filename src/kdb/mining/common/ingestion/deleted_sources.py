#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""入库前的闸门：来源文章已被整篇下架（软删）的，不再插入新知识。

判据是"活跃条数为 0 且有软删记录"。**不能**只看"有没有软删记录"——入库去重本身就会
打掉零星重复条目（实测 235 篇里 103 篇都有这种零星软删），那不是下架。

详见 `function_schema/skip_deleted_sources.*.md`。
"""

import json
import logging
import os
from datetime import datetime

import fire
import requests

VERDICT_SKIP = 'all_deleted'


def _es_conf(es_config):
    cfg = json.load(open(es_config, 'r', encoding='utf-8'))
    return cfg['hosts'][0].rstrip('/'), (cfg.get('username'), cfg.get('password'))


def fetch_source_file_status(names, index_name='wayfair',
                             es_config='config/config_es_engine.json'):
    """按 from_file_name 查每篇文章的活跃/软删条数，给出 verdict。"""
    host, auth = _es_conf(es_config)
    status = {}
    for name in sorted(set(n for n in names if n)):
        body = {
            'size': 0,
            'query': {'bool': {'filter': [
                {'term': {'ext_info.from_file_name.keyword': name}}]}},
            'aggs': {'d': {'terms': {'field': 'del_flag', 'size': 5},
                           'aggs': {'f': {'terms': {'field': 'flag.keyword', 'size': 20}}}}},
        }
        resp = requests.post(f'{host}/{index_name}/_search', auth=auth, json=body, timeout=120)
        resp.raise_for_status()
        buckets = {b['key']: b for b in resp.json()
                   .get('aggregations', {}).get('d', {}).get('buckets', [])}
        alive = buckets.get(0, {}).get('doc_count', 0)
        deleted = buckets.get(1, {}).get('doc_count', 0)
        flags = [f['key'] for f in (buckets.get(1, {}).get('f', {}) or {}).get('buckets', [])]
        if alive == 0 and deleted > 0:
            verdict = VERDICT_SKIP
        elif alive == 0:
            verdict = 'never_indexed'
        elif deleted > 0:
            verdict = 'partial_deleted'
        else:
            verdict = 'ok'
        status[name] = {'alive': alive, 'deleted': deleted, 'verdict': verdict, 'flags': flags}
    return status


def _source_name(payload):
    ext = payload.get('ext_info') or {}
    return ext.get('from_file_name') or payload.get('from_file_name')


def split_by_source_status(input_file, output_keep=None, output_skip=None, field_num=0,
                           index_name='wayfair', es_config='config/config_es_engine.json',
                           output_dir='output/skip_deleted_sources', name_field_num=None):
    """按下架状态把待入库文件拆成 keep / skipped 两份。

    :param field_num: 第几列是 JSON（search_data / segment_knowledge 这类逐条产物）
    :param name_field_num: 第几列**直接就是文件名**（不是 JSON）。给了它就走这条路，
        用于阶段间的映射清单（如 QA 的 `qa_regen_*.txt`：第 1 列是 from_file_name）。
        QA 产物是按文件散在各解析目录里的，没有逐条 JSON 可拆，闸门只能卡在映射清单这一层。
    """
    output_keep = output_keep or input_file + '.keep'
    output_skip = output_skip or input_file + '.skipped'
    os.makedirs(output_dir, exist_ok=True)
    flag = datetime.now().strftime('%Y%m%d_%H%M%S')

    lines = []
    for raw in open(input_file, 'r', encoding='utf-8'):
        raw = raw.rstrip('\n')
        if not raw.strip():
            continue
        columns = raw.split('\t')
        col = field_num if name_field_num is None else name_field_num
        if len(columns) <= col:
            logging.warning(f'字段不足，原样保留: {raw[:120]}')
            lines.append((raw, None))
            continue
        if name_field_num is not None:
            lines.append((raw, columns[name_field_num].strip() or None))
            continue
        try:
            payload = json.loads(columns[field_num])
        except Exception:
            logging.warning(f'JSON 解析失败，原样保留: {raw[:120]}')
            lines.append((raw, None))
            continue
        lines.append((raw, _source_name(payload)))

    status = fetch_source_file_status([n for _, n in lines if n], index_name, es_config)

    kept = skipped = 0
    by_verdict = {}
    with open(output_keep, 'w', encoding='utf-8') as fk, \
            open(output_skip, 'w', encoding='utf-8') as fs:
        for raw, name in lines:
            verdict = (status.get(name) or {}).get('verdict', 'unknown') if name else 'no_source'
            by_verdict.setdefault(verdict, set()).add(name)
            if verdict == VERDICT_SKIP:
                fs.write(raw + '\n')
                skipped += 1
            else:
                fk.write(raw + '\n')
                kept += 1

    report = {
        'input_file': input_file, 'index_name': index_name, 'generated_at': flag,
        'total_lines': len(lines), 'kept_lines': kept, 'skipped_lines': skipped,
        'output_keep': output_keep, 'output_skip': output_skip,
        'verdict_files': {k: sorted(x for x in v if x) for k, v in by_verdict.items()},
        'status': status,
    }
    report_path = os.path.join(output_dir, f'report_{flag}.json')
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    logging.info(f'总行 {len(lines)} | 可插入 {kept} | 跳过（整篇已下架）{skipped}')
    for verdict, files in sorted(by_verdict.items()):
        logging.info(f'  {verdict}: {len([x for x in files if x])} 篇')
    for name in sorted(x for x in by_verdict.get(VERDICT_SKIP, set()) if x):
        info = status[name]
        logging.info(f'  跳过 {name}（已删 {info["deleted"]}，flag={info["flags"]}）')
    logging.info(f'报告: {report_path}')
    return report_path


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(asctime)s: %(message)s', force=True)
    fire.Fire({'split': split_by_source_status, 'status': fetch_source_file_status})
