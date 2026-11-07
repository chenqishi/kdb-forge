#!/usr/bin/env python
# -*- coding:utf8 -*-
"""从入口页发现同站链接（给没有 sitemap 的平台用）。

背景：`prep_platform_sources.py` 靠 sitemap 盘点页面，但实测
Allegro / Wayfair / Kaufland / Joom / Temu / Trendyol / OnBuy / ManoMano / Chewy
这些站 HTTP 200 但没有 sitemap.xml，只能从入口页逐层发现链接。

做法：BFS 两层，只收**同域且路径包含关键词**的链接（帮助/卖家/入驻类），
避免把整站商品页拉进来 —— Bol 那次教训是漏页（只找到 102/752），
这里相反，要防的是**收进无关页面把语料稀释掉**。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('knowledge_crawler_tool/web_crawl/discover_links.py')
import argparse
import html
import logging
import os
import re
import sys
from typing import List, Set
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from knowledge_crawler_tool.web_crawl.crawl_url_list import fetch  # noqa: E402

LOGGER = logging.getLogger(__name__)

# 只要路径里带这些词的页面（卖家/帮助/入驻相关）
# 用词边界，别用裸子串：`fee` 会命中 chewy.com/b/chicken-feed-951（商品分类页），
# `sell` 会命中任意含该串的商品 slug。实测 Chewy 因此抓回 20 篇商品列表、187 万字纯噪声。
_KEEP = re.compile(r'(?:^|[/_\-?&=])('
                   r'help|support|faq|seller|sellers|selling|sell-on|vendor|vendors|'
                   r'partner|partners|merchant|onboard|onboarding|'
                   r'pomoc|sprzedaj|verkauf|vendre|satici|aide|hilfe|'
                   r'guide|guides|policy|policies|requirements|'
                   r'commission|commissions|fees|pricing|shipping|returns|'
                   r'account|register|registration)(?:[/_\-?&=.]|$)', re.I)
# 明显不要的：商品页、登录、法务、社媒
_DROP = re.compile(r'(/b/|/dp/|/s\?|/product|/item|/offer|/login|/signin|/cart|/checkout|'
                   r'privacy|cookie|legal|terms|facebook|twitter|linkedin|instagram|'
                   r'\.(jpg|png|gif|svg|pdf|zip|css|js)($|\?))', re.I)


def links_on(page_url: str, raw: str, host: str) -> Set[str]:
    out = set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\'#]+)', raw, re.I):
        u = html.unescape(m.group(1)).strip()
        if u.startswith(('mailto:', 'tel:', 'javascript:')):
            continue
        full = urljoin(page_url, u)
        p = urlparse(full)
        if p.scheme not in ('http', 'https') or p.netloc != host:
            continue
        full = full.split('#')[0].rstrip('/')
        if _DROP.search(full):
            continue
        out.add(full)
    return out


def discover(entry: str, max_pages: int = 300, depth: int = 2) -> List[str]:
    host = urlparse(entry).netloc
    seen: Set[str] = set()
    keep: Set[str] = set()
    frontier = [entry.rstrip('/')]
    for lvl in range(depth):
        nxt: Set[str] = set()
        for u in frontier:
            if u in seen or len(keep) >= max_pages:
                continue
            seen.add(u)
            raw = fetch(u, timeout=25, retries=2)
            if not raw:
                continue
            found = links_on(u, raw, host)
            for f in found:
                if _KEEP.search(f):
                    keep.add(f)
                nxt.add(f)
            LOGGER.info('第%s层 %s → 发现 %s 链接，累计保留 %s', lvl + 1, u[:60], len(found), len(keep))
        frontier = [u for u in nxt if u not in seen][:120]
        if not frontier:
            break
    keep.add(entry.rstrip('/'))
    return sorted(keep)[:max_pages]


def main():
    ap = argparse.ArgumentParser(description='无 sitemap 站点的链接发现')
    ap.add_argument('--entry', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max-pages', type=int, default=300)
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--log-level', default='WARNING')
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING),
                        format='%(asctime)s %(levelname)s %(message)s')

    urls = discover(args.entry, args.max_pages, args.depth)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(urls))
    print(f'{args.entry} → 发现 {len(urls)} 个候选页 → {args.out}')


if __name__ == '__main__':
    main()
