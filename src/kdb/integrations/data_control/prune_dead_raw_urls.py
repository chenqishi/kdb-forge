#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""删掉知识正文里那些**指向不存在对象**的裸图片 URL。默认 dry-run。

和 `prune_page_mismatched_images.py` 是两类正交的问题
--------------------------------------------------
那个工具处理的是 `[multimodal_prefix]<path>` 标记——图挂错页。
本工具处理的是**裸 URL 文本**：它躺在 `multimodal_contents` 的 **text 项**文字里，
拼接时当普通正文接上，从来不是 image 项，所以按标记处理的工具碰不到它，
按页裁图也裁不掉它。

来源（实测定位）
----------------
任务没开图片占位符模式时，解析正文里图片位置放的是裸 URL，让模型抄进答案。
模型抄 32 位 hash 会抄错：实测 `f655370b` 那条真图是 `0da69b79…`，
模型写成 `3da69b79…`，逐位只差 1/32，对应的对象从不存在，必然 404。

判据只有一个：实际发 HEAD 请求
------------------------------
「有没有 `?filename=` 后缀」「hash 长得像不像」这类特征都不能用：
库里存的全是裸 URL，`?filename=` 是检索服务返回时才拼的；
而 hash 抄错一位和正常 hash 在形态上没有区别。

提取必须按 `https://` 边界非贪婪切分
-----------------------------------
正文里多个 URL 是**无分隔符直接粘在一起**的
（`….pnghttps://file.marsmind.cc/…`）。贪婪正则会跨过 URL 边界，
把拼接串当成一个 URL 去测——那当然 404。
栽过一次：错切出 184 个串、报 171 个死链，正确切分后是 1015 个 URL、32 个死链。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/prune_dead_raw_urls.py')

import argparse
import collections
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))

from commons.es_http_client import EsHttpClient

logging.basicConfig(level=logging.INFO,
                    format='[%(levelname)s] [%(asctime)s] %(message)s')

# 非贪婪到图片扩展名为止，且中途不许再出现 http —— 必须这样才能切开粘连的 URL
RAW_IMAGE_URL = re.compile(
    r'https?://(?:(?!https?://)[^\s"\'）)\]，。；,])*?\.(?:jpg|jpeg|png|gif|bmp|webp)', re.I)

# 已知坏样本，用作被测集合的金丝雀。集合里没有它就说明圈定漏了。
CANARY = '3da69b7917e749969866e010b29d5c2a'

# 写回批次控小：阿里云 ES Serverless 单请求 15MB 上限，partial update 也带 1024 维向量
DEFAULT_BULK_BATCH = 50


def extract_raw_image_urls(text: str) -> List[str]:
    """从一段文字里切出裸图片 URL，按出现顺序、去重。"""
    seen: Set[str] = set()
    out: List[str] = []
    for match in RAW_IMAGE_URL.finditer(text or ''):
        url = match.group(0)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def join_multimodal_contents(multimodal_contents: Sequence[Dict[str, Any]]) -> str:
    """复刻 `SearchDataInterface.join_multimodal_contents` 的拼接规则。

    入库时 `content` 就是这么拼出来的，所以改完 `multimodal_contents` 用它重拼，
    content 与结构化字段天然一致，不会出现「标记数≠图数」。

    **调用方必须先用 `rebuild_matches_current` 自检**：拿未修改的
    `multimodal_contents` 重拼一遍，能逐字复现现有 content 才可以用。
    """
    content = ''
    for item in multimodal_contents:
        if item.get('type') == 'text':
            piece = item.get('content')
            content = f'{content}\n{piece}' if content else piece
        elif item.get('type') in ('image', 'video', 'audio', 'file'):
            address = (f'[multimodal_prefix]{item["path"]}' if item.get('path')
                       else item.get('url'))
            if not address:
                continue
            content = f'{content}\n{address}' if content else address
    return content or ''


def rebuild_matches_current(multimodal_contents: Sequence[Dict[str, Any]],
                            current_content: str) -> bool:
    """自检：用现有 multimodal_contents 重拼，能否逐字复现现有 content。

    不一致说明这条记录的 content 不是（或不完全是）拼接产物，
    本工具就不该改它——跳过交人工，不要赌。
    """
    return join_multimodal_contents(multimodal_contents) == (current_content or '')


def strip_urls_from_text(text: str, dead: Set[str]) -> str:
    """把死链从文字里删掉，并收拾残留的空行/行尾空白。

    实测这些 URL 的位置形态：独占一行 149 次、后面紧跟另一个 URL 26 次、
    行尾在冒号之后 1 次、**夹在句子中间 0 次**。所以直接删不会断句。
    """
    out = text or ''
    for url in sorted(dead, key=len, reverse=True):
        out = out.replace(url, '')
    out = re.sub(r'[ \t]+\n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    # 删完只剩空白的行去掉
    lines = [l for l in out.split('\n')]
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines).rstrip()


def has_dangling_colon(text: str, dead: Set[str]) -> bool:
    """删完之后是否留下「以冒号结尾、后面什么都没有」的悬空句。"""
    cleaned = strip_urls_from_text(text, dead)
    return bool(re.search(r'[:：]\s*$', cleaned))


def surgery_on_content(content: str, dead: Set[str]) -> Optional[str]:
    """兜底：不重拼，直接把死链子串从 content 里删掉。

    用于 `multimodal_contents` 的**列表顺序与 content 里的顺序不一致**的记录
    （实测有 4 行是 text1 + 图 + text2，而列表里 text 项被排在一起），
    这种按列表顺序重拼会打乱正文，只能就地删。

    返回 None 表示校验没过：新旧 content 的差异不是「恰好少了这些 URL」，不能改。
    """
    new = strip_urls_from_text(content, dead)

    # 校验：新旧 content 的差异必须**恰好只是这些 URL**（忽略空白）。
    # 不过就说明删除动作影响到了别的文字，不能改。
    def norm(text: str) -> str:
        out = text
        for url in sorted(dead, key=len, reverse=True):
            out = out.replace(url, '')
        return re.sub(r'\s+', '', out)
    if norm(content) != re.sub(r'\s+', '', new):
        return None
    return new


def clean_multimodal(multimodal_contents: Sequence[Dict[str, Any]],
                     dead: Set[str]) -> Tuple[List[Dict[str, Any]], int]:
    """只改 text 项里的文字，image 项一律不动。返回 (新列表, 删掉的 URL 次数)。"""
    out: List[Dict[str, Any]] = []
    removed = 0
    for item in multimodal_contents:
        if (item.get('type') or 'text') != 'text':
            out.append(item)
            continue
        text = item.get('content') or ''
        present = [u for u in extract_raw_image_urls(text) if u in dead]
        if not present:
            out.append(item)
            continue
        new_item = dict(item)
        new_item['content'] = strip_urls_from_text(text, set(present))
        removed += len(present)
        out.append(new_item)
    return out, removed


def probe_urls(urls: Sequence[str], workers: int = 8,
               timeout: int = 15) -> Dict[str, int]:
    """并发 HEAD 实测。返回 {url: status_code}，请求异常记 -1。"""
    session = requests.Session()

    def probe(url: str) -> Tuple[str, int]:
        try:
            return url, session.head(url, timeout=timeout, allow_redirects=True).status_code
        except Exception:  # noqa: BLE001 - 网络异常也算不可达
            return url, -1

    out: Dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, code in pool.map(probe, list(urls)):
            out[url] = code
    return out


# ---------------------------------------------------------------------------
# 跑批
# ---------------------------------------------------------------------------

def collect_rows(es: EsHttpClient, index: str,
                 task_ids: Optional[Sequence[str]] = None):
    """拉活跃知识里、`multimodal_contents` 的 text 项含裸图片 URL 的行。"""
    must: List[Dict[str, Any]] = [{'term': {'del_flag': 0}}]
    if task_ids:
        must.append({'terms': {'task_id': list(task_ids)}})
    query = {'bool': {'must': must}}
    fields = ['content', 'multimodal_contents', 'title', 'task_id',
              'data_type', 'audit_result', 'quality_level', 'ext_info']
    for doc_id, src in es.iter_search_after(index, query, fields, page_size=500):
        urls: List[str] = []
        for item in src.get('multimodal_contents') or []:
            if (item.get('type') or 'text') == 'text':
                urls += extract_raw_image_urls(item.get('content') or '')
        if urls:
            yield doc_id, src, sorted(set(urls))


def run(config_path: str, index: str, work_dir: str,
        embedding_config: str = 'config/config_ali_embedding.json',
        task_ids: Optional[Sequence[str]] = None,
        bulk_batch: int = DEFAULT_BULK_BATCH,
        execute: bool = False) -> Dict[str, Any]:
    """扫 → 实测 → 清 text 项里的死链 → 重拼 content → 重算 embedding。默认 dry-run。"""
    es = EsHttpClient.from_config(config_path)
    os.makedirs(work_dir, exist_ok=True)

    rows = list(collect_rows(es, index, task_ids))
    all_urls = sorted({u for _, _, us in rows for u in us})
    logging.info('含裸图片 URL 的活跃行 %d；不重复裸 URL %d', len(rows), len(all_urls))

    # 金丝雀：被测集合里必须有已知坏样本，否则说明圈定漏了，
    # 否则「0 死链」这个结论会自洽地骗人（栽过一次）。
    if not any(CANARY in u for u in all_urls):
        raise RuntimeError('金丝雀 %s 不在被测集合里 —— URL 提取或圈定口径有问题，拒绝继续'
                           % CANARY)
    logging.info('金丝雀自检通过：%s 在被测集合里', CANARY[:12])

    code = probe_urls(all_urls)
    dead = {u for u, c in code.items() if c != 200}
    logging.info('实测非 200 的裸 URL %d / %d；状态码分布 %s',
                 len(dead), len(all_urls), dict(collections.Counter(code.values())))

    plans: List[Dict[str, Any]] = []
    stats = collections.Counter()
    for doc_id, src, urls in rows:
        row_dead = {u for u in urls if u in dead}
        if not row_dead:
            continue
        stats['含死链的行'] += 1
        mm = src.get('multimodal_contents') or []
        content = src.get('content') or ''
        new_mm, removed = clean_multimodal(mm, row_dead)
        if rebuild_matches_current(mm, content):
            # content 是纯拼接产物：改完 mm 重拼，两者天然一致
            new_content = join_multimodal_contents(new_mm)
            stats['修法_重拼'] += 1
        else:
            # mm 列表顺序与 content 顺序不一致，重拼会打乱正文，只能就地删
            surgery = surgery_on_content(content, row_dead)
            if surgery is None:
                stats['跳过_就地删校验未过'] += 1
                plans.append({'_id': doc_id, 'action': 'review_not_joinable',
                              'title': (src.get('title') or '')[:60],
                              'task_id': (src.get('task_id') or '')[:8],
                              'dead': sorted(row_dead)})
                continue
            new_content = surgery
            stats['修法_就地删'] += 1
        dangling = any(has_dangling_colon(i.get('content') or '', row_dead)
                       for i in mm if (i.get('type') or 'text') == 'text')
        prose_left = bool(re.sub(r'\[multimodal_prefix\][^\s\]]+', '', new_content).strip())
        action = 'prune'
        if not new_content.strip():
            action = 'review_empty'
        elif dangling:
            action = 'review_dangling_colon'
        elif not prose_left:
            action = 'review_no_text'
        stats['action_' + action] += 1
        stats['删掉死链次数'] += removed
        plans.append({'_id': doc_id, 'action': action,
                      'title': (src.get('title') or '')[:60],
                      'task_id': (src.get('task_id') or '')[:8],
                      'data_type': src.get('data_type'),
                      'audit_result': src.get('audit_result'),
                      'dead': sorted(row_dead),
                      'content_before': content, 'content_after': new_content,
                      'multimodal_after': new_mm})

    plan_file = os.path.join(work_dir, 'plan_dead_raw_urls.json')
    with open(plan_file, 'w', encoding='utf-8') as handle:
        json.dump(plans, handle, ensure_ascii=False, indent=2)
    for key in sorted(stats):
        logging.info('  %-24s %d', key, stats[key])
    logging.info('方案已写 %s', plan_file)

    result: Dict[str, Any] = {'stats': dict(stats), 'plan_file': plan_file,
                              'dead_urls': len(dead), 'probed_urls': len(all_urls)}
    if not execute:
        result['dry_run'] = True
        logging.info('[dry-run] 未写回，加 --execute 才改 ES')
        return result

    from commons.embedding_tools import AliEmbedding
    embedder = AliEmbedding(embedding_config)
    rollback_file = os.path.join(work_dir, 'rollback_dead_raw_urls.jsonl')
    updates: List[Tuple[str, Dict[str, Any]]] = []
    errors: List[Dict[str, str]] = []
    with open(rollback_file, 'w', encoding='utf-8') as rb:
        for plan in plans:
            if plan['action'] != 'prune':
                continue
            try:
                rb.write(json.dumps({'_id': plan['_id'],
                                     'content': plan['content_before']},
                                    ensure_ascii=False) + '\n')
                emb = embedder.text2embedding(plan['content_after'])
                try:
                    emb = emb.reshape(-1).tolist()
                except AttributeError:
                    emb = list(emb)
                updates.append((plan['_id'], {
                    'content': plan['content_after'],
                    'multimodal_contents': plan['multimodal_after'],
                    'content_embedding': emb}))
            except Exception as exc:  # noqa: BLE001 - 单行失败不中断整批
                logging.error('行 %s 处理失败，跳过: %s', plan['_id'], exc)
                errors.append({'_id': plan['_id'], 'error': str(exc)[:200]})
    logging.info('回滚文件 %s；待写回 %d 行，处理失败 %d 行',
                 rollback_file, len(updates), len(errors))
    bulk = es.bulk_update_doc(index, updates, batch_size=bulk_batch)
    result.update({'updated': bulk.get('updated', 0), 'failed': bulk.get('failed', []),
                   'rollback_file': rollback_file, 'row_errors': errors})
    logging.info('写回完成 updated=%d failed=%d', result['updated'], len(result['failed']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', default='config/config_es_engine.json')
    parser.add_argument('--embedding_config', default='config/config_ali_embedding.json')
    parser.add_argument('--index', required=True)
    parser.add_argument('--work_dir', required=True)
    parser.add_argument('--task_ids', default=None, help='逗号分隔，默认全库')
    parser.add_argument('--bulk_batch', type=int, default=DEFAULT_BULK_BATCH)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    tids = [x.strip() for x in args.task_ids.split(',')] if args.task_ids else None
    out = run(args.config, args.index, args.work_dir, args.embedding_config,
              tids, args.bulk_batch, args.execute)
    print(json.dumps({k: v for k, v in out.items() if k not in ('failed',)},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
