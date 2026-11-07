#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""剥离段落知识开头的站点导航样板，并同步重算向量。默认 dry-run。

firecrawl 抓 markdown 会把 cookie 横幅 + 左侧导航放在每页正文开头，段落切分正好切到
页首那一块时就会带上。这些段落**不是纯样板**——剥离后仍有上千字实质内容，所以只能剥前缀，
不能整条删。

详见 `function_schema/strip_nav_boilerplate.*.md`。
"""

import json
import logging
import os
from datetime import datetime

import fire
import requests

from commons.embedding_tools import AliEmbedding

# 判定"这条含导航样板"的特征串。只用 cookie 横幅的开头句：
# 「所有主题」「API 实验场」这类词正文里也会出现（如「所有主题 # Dropship Orders API」），
# 拿它们当特征会把正常段落误判成样板。
DEFAULT_BOILER_MARKERS = ['本网站使用 Cookie 来评估和改善网站性能']
# 导航块最后一条链接的 URL。用 URL 而不是链接文字「词汇表」定位：
# 词汇表页面的正文标题本身就是 `**词汇表**`，用文字匹配会 rfind 到正文标题并把它切掉。
DEFAULT_TAIL_MARKERS = ['posts/glossary)']
MIN_BODY_CHARS = 50


def find_nav_prefix_end(content, tail_markers=None, max_prefix_ratio=0.5, max_prefix_chars=3000):
    """定位导航样板结束位置；无法可靠定位返回 None（宁可跳过也不瞎切）。

    marker 应当能唯一命中导航块的**最后一行**，正文从该行的下一行开始。
    """
    if not content:
        return None
    tail_markers = tail_markers or DEFAULT_TAIL_MARKERS

    pos = -1
    for marker in tail_markers:
        found = content.rfind(marker)
        if found > pos:
            pos = found
    if pos < 0:
        return None

    line_end = content.find('\n', pos)
    if line_end < 0:
        return None
    end = line_end + 1

    # 安全阀：这些段落含真内容，定位错了就会切掉真知识
    if end > max_prefix_chars or end > len(content) * max_prefix_ratio:
        return None
    if len(content) - end < MIN_BODY_CHARS:
        return None
    return end


def _es_conf(es_config):
    cfg = json.load(open(es_config, 'r', encoding='utf-8'))
    return cfg['hosts'][0].rstrip('/'), (cfg.get('username'), cfg.get('password'))


def _scroll_docs(host, auth, index_name, task_id):
    """search_after 翻页拉全部活跃文档。"""
    docs, after = [], None
    while True:
        body = {
            'query': {'bool': {'filter': [{'term': {'task_id.keyword': task_id}},
                                          {'term': {'del_flag': 0}}]}},
            'size': 500, 'sort': [{'_id': 'asc'}],
            '_source': ['content', 'data_type', 'multimodal_contents', 'ext_info.from_file_name'],
        }
        if after:
            body['search_after'] = after
        resp = requests.post(f'{host}/{index_name}/_search', auth=auth, json=body, timeout=120)
        resp.raise_for_status()
        hits = resp.json()['hits']['hits']
        if not hits:
            break
        docs += hits
        after = hits[-1]['sort']
    return docs


def run(task_id, index_name='wayfair', execute=False, output_dir='output/strip_nav_boilerplate',
        es_config='config/config_es_engine.json',
        embedding_config='config/config_ali_embedding.json',
        boiler_markers=None):
    """剥离导航样板。默认 dry-run，execute=True 才写库。"""
    boiler_markers = list(boiler_markers) if boiler_markers else DEFAULT_BOILER_MARKERS
    os.makedirs(output_dir, exist_ok=True)
    flag = datetime.now().strftime('%Y%m%d_%H%M%S')
    host, auth = _es_conf(es_config)

    docs = _scroll_docs(host, auth, index_name, task_id)
    # data_type 没有 keyword 索引，term/agg 查不到，只能客户端过滤
    def _has_boiler(text):
        return bool(text) and any(m in text for m in boiler_markers)

    targets = []
    for hit in docs:
        src = hit['_source']
        if src.get('data_type') != 'segment':
            continue
        # multimodal_contents 是多段结构（文本/图片交替）时与 content 并不逐字相同，
        # 样板可能只残留在某一段里，所以两处都要查
        parts = src.get('multimodal_contents') or []
        if _has_boiler(str(src.get('content') or '')) or \
                any(_has_boiler(str(p.get('content') or '')) for p in parts if isinstance(p, dict)):
            targets.append(hit)
    logging.info(f'活跃文档 {len(docs)}，其中含样板的段落 {len(targets)}')

    embedder = AliEmbedding(embedding_config) if execute else None
    rollback_path = os.path.join(output_dir, f'rollback_{flag}.jsonl')
    rollback_file = open(rollback_path, 'w', encoding='utf-8') if execute else None

    items, stripped, skipped, failed = [], 0, 0, 0
    for hit in targets:
        doc_id, src = hit['_id'], hit['_source']
        content = str(src.get('content') or '')
        end = find_nav_prefix_end(content) if _has_boiler(content) else None
        new_content = content[end:] if end else content

        # 逐段剥离：多段结构下样板可能只在其中一段
        old_parts = src.get('multimodal_contents')
        new_parts, parts_changed = old_parts, 0
        if isinstance(old_parts, list) and old_parts:
            new_parts = json.loads(json.dumps(old_parts, ensure_ascii=False))
            for part in new_parts:
                if not isinstance(part, dict):
                    continue
                text = str(part.get('content') or '')
                if not _has_boiler(text):
                    continue
                # 分段级放宽占比阀：单个分段完全可能大部分是导航块（实测 878 字符的段里
                # 764 是导航），整篇正文那档 0.5 的阀值在这里会误拒。MIN_BODY_CHARS 仍在兜底。
                part_end = find_nav_prefix_end(text, max_prefix_ratio=0.95)
                if part_end:
                    part['content'] = text[part_end:]
                    parts_changed += 1

        content_changed = end is not None
        record = {
            'id': doc_id,
            'url': (src.get('ext_info') or {}).get('from_file_name'),
            'old_len': len(content),
            'prefix_len': end,
            'new_len': (len(content) - end) if end else len(content),
            'parts_changed': parts_changed,
            'old_head': content[:60].replace('\n', ' '),
            'new_head': new_content[:60].replace('\n', ' '),
            'status': 'pending',
        }
        if not content_changed and not parts_changed:
            record['status'] = 'skipped'
            record['reason'] = '无法可靠定位导航块结尾，需人工处理'
            skipped += 1
            items.append(record)
            continue

        if not execute:
            record['status'] = 'dry_run'
            stripped += 1
            items.append(record)
            continue

        try:
            rollback_file.write(json.dumps({
                'id': doc_id, 'content': content,
                'multimodal_contents': src.get('multimodal_contents'),
            }, ensure_ascii=False) + '\n')
            rollback_file.flush()

            doc = {}
            if content_changed:
                embedding = embedder.text2embedding(new_content)
                if embedding is None:
                    raise RuntimeError('向量重算返回 None')
                doc['content'] = new_content
                doc['content_embedding'] = embedding.tolist()
            if parts_changed:
                doc['multimodal_contents'] = new_parts

            resp = requests.post(f'{host}/{index_name}/_update/{doc_id}', auth=auth,
                                 json={'doc': doc}, timeout=120)
            body = resp.json()
            if resp.status_code >= 300 or body.get('error'):
                raise RuntimeError(f'ES update 失败: {str(body)[:200]}')
            record['status'] = 'stripped'
            stripped += 1
        except Exception as exc:
            record['status'] = 'failed'
            record['reason'] = f'{type(exc).__name__}: {exc}'
            failed += 1
            logging.error(f'{doc_id} 处理失败: {record["reason"]}')
        items.append(record)

    if rollback_file:
        rollback_file.close()

    report = {
        'task_id': task_id, 'index_name': index_name, 'execute': execute,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'total_active_docs': len(docs), 'boilerplate_segments': len(targets),
        'stripped': stripped, 'skipped': skipped, 'failed': failed,
        'rollback_file': rollback_path if execute else None,
        'items': items,
    }
    report_path = os.path.join(output_dir, f'report_{"execute" if execute else "dryrun"}_{flag}.json')
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    logging.info(f'含样板 {len(targets)} | 剥离 {stripped} | 跳过 {skipped} | 失败 {failed}')
    logging.info(f'报告: {report_path}')
    return report_path


def rollback(rollback_file, index_name='wayfair', es_config='config/config_es_engine.json',
             embedding_config='config/config_ali_embedding.json'):
    """按回滚文件恢复原文，并按原文重算向量（向量可确定性复现，故只需存文本）。"""
    host, auth = _es_conf(es_config)
    embedder = AliEmbedding(embedding_config)
    done = failed = 0
    for line in open(rollback_file, 'r', encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        try:
            embedding = embedder.text2embedding(rec['content'])
            doc = {'content': rec['content'], 'content_embedding': embedding.tolist()}
            if rec.get('multimodal_contents') is not None:
                doc['multimodal_contents'] = rec['multimodal_contents']
            resp = requests.post(f'{host}/{index_name}/_update/{rec["id"]}', auth=auth,
                                 json={'doc': doc}, timeout=120)
            if resp.status_code >= 300 or resp.json().get('error'):
                raise RuntimeError(str(resp.json())[:200])
            done += 1
        except Exception as exc:
            failed += 1
            logging.error(f'{rec["id"]} 回滚失败: {exc}')
    logging.info(f'回滚完成 {done}，失败 {failed}')
    return done


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)s] %(asctime)s: %(message)s', force=True)
    fire.Fire({'run': run, 'rollback': rollback})
