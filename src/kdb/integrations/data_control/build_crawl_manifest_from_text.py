#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
把「纯文本爬取产物」转成 `build_doc_mining_tasks.py` 能吃的 crawl_manifest 格式。

背景：`build_doc_mining_tasks.py` 只认 `login_doc_crawler` 的产出形态
（`crawl_manifest.json` + 每篇一个目录、内含 `content.md` / `meta.json`），
而 `bol_partner_portal_fetch.py` 这类轻量爬虫产出的是扁平的 `<slug>.txt`。
本脚本做格式适配，不改动上游任何一方。

顺带做**灌库前的质量闸门**（"合格才灌"）：
- 正文过短的丢掉（切不出有效 QA，只会污染库）
- **时效性内容默认丢掉**：`nadp` 类政策变更公告、节日/活动页写的是"某月起变更"，
  灌进知识库会过期且没人会回来清理。要留就显式 `--keep-timely`。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('data_control_tools/build_crawl_manifest_from_text.py')

import argparse
import json
import logging
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

LOGGER = logging.getLogger(__name__)

# 时效性信号：标题/正文命中即视为「会过期」的内容
_TIMELY_TITLE_RE = re.compile(
    r'holiday|christmas|black.?friday|sinterklaas|webinar|event|summit|'
    r'thank.?you|closing|deadline|this changes|changes? (in|to) our|'
    r'as of \d|per \d{1,2} \w+|20\d\d q[1-4]|season',
    re.I)
# 正文里的时效表述。注意**只认「未来/近期生效」**：
# "From 1 February 2021" 这种**过去生效日**说明规则早已长期有效，不是会过期的公告，
# 误杀它会把一大批 assortment-policy（品类上架规则）整片丢掉——实测踩过。
_TIMELY_BODY_RE = re.compile(
    r'(this|next) (quarter|month) (we|the)|will change (on|per)|'
    r'(as of|starting|from) \d{1,2} \w+ 20(2[5-9]|[3-9]\d)|'
    r'(as of|starting|from) (january|february|march|april|may|june|july|august|'
    r'september|october|november|december) 20(2[5-9]|[3-9]\d)',
    re.I)


def is_timely(title: str, body: str) -> Tuple[bool, str]:
    """判断是否属于会过期的时效性内容。"""
    m = _TIMELY_TITLE_RE.search(title or '')
    if m:
        return True, f'标题命中时效词 {m.group(0)!r}'
    m = _TIMELY_BODY_RE.search((body or '')[:1500])
    if m:
        return True, f'正文命中时效表述 {m.group(0)!r}'
    return False, ''


# 短但仍有价值的页：正文虽短，但讲的是规则/资格/流程本身（枢纽页会给出关键定性）。
# 实测 `partner-non-eu` 只有 364 字符却是非欧盟卖家 VAT 规则的入口，误杀它等于丢掉
# 中国卖家最相关的那一类内容。
_WORTH_SHORT_RE = re.compile(
    r'non-eu|vat|invoice|tax|registration|requirement|eligib|deemed supplier|'
    r'commission|payment|policy', re.I)


def _is_worth_keeping_short(title: str, body: str) -> bool:
    return bool(_WORTH_SHORT_RE.search(title or '')) and len((body or '').strip()) >= 150


def load_text_docs(src_dir: str, min_chars: int = 400,
                   keep_timely: bool = False) -> Tuple[List[dict], Dict[str, int]]:
    """扫描 `<slug>.txt`，返回通过质量闸门的文档列表与统计。"""
    manifest = {}
    mpath = os.path.join(src_dir, 'manifest.json')
    if os.path.exists(mpath):
        with open(mpath, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        for rec in raw.values():
            if isinstance(rec, dict) and rec.get('slug'):
                manifest[rec['slug']] = rec

    docs, stats = [], {'total': 0, 'too_short': 0, 'timely': 0, 'kept': 0}
    for name in sorted(os.listdir(src_dir)):
        if not name.endswith('.txt'):
            continue
        stats['total'] += 1
        slug = name[:-4]
        with open(os.path.join(src_dir, name), 'r', encoding='utf-8') as f:
            raw = f.read()
        parts = raw.split('\n\n', 1)
        title = parts[0].strip()
        body = (parts[1] if len(parts) > 1 else '').strip()

        if len(body) < min_chars and not _is_worth_keeping_short(title, body):
            stats['too_short'] += 1
            LOGGER.info('丢弃(过短 %d): %s', len(body), slug)
            continue
        if not keep_timely:
            timely, why = is_timely(title, body)
            if timely:
                stats['timely'] += 1
                LOGGER.info('丢弃(时效性 %s): %s', why, slug)
                continue

        stats['kept'] += 1
        docs.append({
            'slug': slug, 'title': title, 'body': body,
            'url': (manifest.get(slug) or {}).get('url', ''),
        })
    return docs, stats


def write_manifest(docs: List[dict], out_dir: str, platform: str,
                   source_name: str) -> str:
    """按 login_doc_crawler 的形态写出 manifest + 每篇一个目录。"""
    os.makedirs(out_dir, exist_ok=True)
    records = []
    for doc in docs:
        doc_dir = os.path.join(out_dir, doc['slug'])
        os.makedirs(doc_dir, exist_ok=True)
        # content.md：小节标记 '## ' 原样保留，正好是 markdown 标题
        with open(os.path.join(doc_dir, 'content.md'), 'w', encoding='utf-8') as f:
            f.write(f"# {doc['title']}\n\n{doc['body']}\n")
        meta = {'title': doc['title'], 'url': doc['url'],
                'platform': platform, 'site': doc['slug'], 'source': source_name}
        with open(os.path.join(doc_dir, 'meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        records.append({'status': 'ok', 'platform': platform, 'site': doc['slug'],
                        'dir': doc_dir, 'url': doc['url'], 'title': doc['title']})

    manifest_path = os.path.join(out_dir, 'crawl_manifest.json')
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({'source': source_name, 'docs': records}, f,
                  ensure_ascii=False, indent=2)
    return manifest_path


def main():
    ap = argparse.ArgumentParser(description='纯文本爬取产物 → crawl_manifest 适配')
    ap.add_argument('--src-dir', required=True, help='含 <slug>.txt 的目录')
    ap.add_argument('--out-dir', required=True, help='输出目录（会生成 crawl_manifest.json）')
    ap.add_argument('--platform', required=True, help='平台名，会写进 meta 与任务类目')
    ap.add_argument('--source-name', default='', help='来源标记，默认同 platform')
    ap.add_argument('--min-chars', type=int, default=400, help='正文最少字符，低于则丢弃')
    ap.add_argument('--keep-timely', action='store_true',
                    help='保留时效性内容（政策变更公告/活动页），默认丢弃')
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    docs, stats = load_text_docs(args.src_dir, min_chars=args.min_chars,
                                 keep_timely=args.keep_timely)
    if not docs:
        raise SystemExit('没有通过质量闸门的文档')

    path = write_manifest(docs, args.out_dir, args.platform,
                          args.source_name or args.platform)
    print(f"扫描 {stats['total']} 篇 → 丢弃 过短 {stats['too_short']} / "
          f"时效性 {stats['timely']} → **保留 {stats['kept']} 篇**")
    print(f'manifest: {path}')


if __name__ == '__main__':
    main()
