from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""为 payoneer_olive 各平台备候选资料源（只探测+盘点，不爬正文）。

用途：348 条缺口分布在 24 个平台，Bol 已在挖掘中，其余平台要先把"从哪儿爬"确定下来。
本脚本对每个候选站点做三件事：
1. **可达性**：HTTP 状态（403/429 表示有反爬，需要 firecrawl 而不是裸 requests）
2. **sitemap 盘点**：`sitemap.xml` 及其子 sitemap 的页面总数
   —— **这条是 Bol 那次的教训**：只靠首页导航发现链接，Bol 只找到 102 页，
   而 sitemap 里有 752 页，漏了 87%。
3. **中文版探测**：有中文页就优先用，可省掉翻译阶段（也更贴近中国卖家读者）

产出 `candidate_sources.json`，供后续按平台逐个爬取。
"""

import argparse
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests

PROJECT_ROOT = str(_PROJECT_ROOT)

LOGGER = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

# 各平台的官方卖家资料入口。带多个候选是因为不同平台命名差异很大，
# 探测后按可达性和页数挑最好的那个。
CANDIDATES: Dict[str, List[str]] = {
    'BestBuy':   ['https://partners.bestbuy.com'],
    'Allegro':   ['https://allegro.pl/pomoc/dla-sprzedajacych',
                  'https://allegro.pl/dla-sprzedajacych'],
    'Walmart':   ['https://marketplace.walmart.com'],
    'Amazon':    ['https://sell.amazon.com', 'https://sellercentral.amazon.com/help'],
    'ManoMano':  ['https://www.manomano.fr/vendre', 'https://sellers.manomano.com'],
    'eBay':      ['https://www.ebay.com/sellercenter', 'https://export.ebay.com'],
    'Wayfair':   ['https://partners.wayfair.com', 'https://www.wayfair.com/supplier'],
    'Lowes':     ['https://sellers.lowes.com', 'https://www.lowes.com/l/sell-on-lowes'],
    'OnBuy':     ['https://www.onbuy.com/gb/sell'],
    'Joom':      ['https://www.joom.com/en/sellers', 'https://merchant.joom.com'],
    'OTTO':      ['https://sell.otto.market', 'https://www.otto.market'],
    'Kaufland':  ['https://sellerportal.kaufland.de', 'https://www.kaufland.de/verkaeuferportal'],
    'Chewy':     ['https://www.chewy.com/app/content/vendor'],
    'Cdiscount': ['https://www.cdiscount.com/vendeur', 'https://sellers.cdiscount.com'],
}


def fetch(url: str, timeout: int = 20) -> Optional[requests.Response]:
    try:
        return requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None


def sitemap_urls(base: str, timeout: int = 25) -> List[str]:
    """取 sitemap 里的所有页面 URL，自动跟进 sitemap index（一层）。"""
    out: List[str] = []
    resp = fetch(base.rstrip('/') + '/sitemap.xml', timeout=timeout)
    if not resp or resp.status_code != 200:
        return out
    locs = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', resp.text)
    # 区分 sitemap index（<sitemapindex> 根）和普通 urlset：
    # 只有 index 才需要跟进子 sitemap。实测 sell.amazon.com 是 urlset（399 个真实页），
    # 若按"含 sitemap 字样就当子 sitemap"去跟进，会把真实页面全过滤掉、得出 0 页的错误结论。
    is_index = '<sitemapindex' in resp.text[:2000].lower()
    subs = [l for l in locs if l.lower().endswith('.xml')] if is_index else []
    if subs:
        for sub in subs[:10]:                    # 只跟前 10 个子 sitemap，避免爆量
            r2 = fetch(sub.replace('&amp;', '&'), timeout=timeout)
            if r2 and r2.status_code == 200:
                out.extend(re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', r2.text))
    else:
        out.extend(locs)
    return [u for u in out if not u.lower().endswith('.xml')]


def probe(platform: str, urls: List[str]) -> dict:
    best = {'platform': platform, 'reachable': False, 'url': '', 'status': None,
            'sitemap_pages': 0, 'zh_pages': 0, 'needs_firecrawl': False, 'tried': []}
    for u in urls:
        resp = fetch(u)
        status = resp.status_code if resp else None
        best['tried'].append({'url': u, 'status': status})
        if status is None:
            continue
        # 403/429 = 有反爬，裸 requests 拿不到，但 firecrawl 通常可以
        needs_fc = status in (403, 429)
        if status == 200 or needs_fc:
            pages = sitemap_urls(u)
            zh = [p for p in pages if re.search(r'/zh[-_]?(hans|cn)?/', p, re.I)]
            if pages or not best['reachable']:
                best.update({'reachable': True, 'url': u, 'status': status,
                             'sitemap_pages': len(pages), 'zh_pages': len(zh),
                             'needs_firecrawl': needs_fc})
            if pages:
                break
    return best


def main():
    ap = argparse.ArgumentParser(description='为各平台备候选资料源（只探测不爬正文）')
    ap.add_argument('--out', default=os.path.join(PROJECT_ROOT, 'data', 'payoneer_olive',
                                                  'candidate_sources.json'))
    ap.add_argument('--only', default='', help='逗号分隔的平台名，默认全部')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    want = {x.strip() for x in args.only.split(',') if x.strip()}
    items = [(p, u) for p, u in CANDIDATES.items() if not want or p in want]

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for r in pool.map(lambda it: probe(*it), items):
            results.append(r)
            print('%-11s %-6s sitemap %4d 页 (中文 %2d) %s %s' % (
                r['platform'], r['status'], r['sitemap_pages'], r['zh_pages'],
                '[需firecrawl]' if r['needs_firecrawl'] else '',
                r['url']), flush=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok = [r for r in results if r['sitemap_pages'] > 0]
    print(f'\n可直接爬（sitemap 有页）：{len(ok)} / {len(results)}')
    print('输出:', args.out)


if __name__ == '__main__':
    main()
