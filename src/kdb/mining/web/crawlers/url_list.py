from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""按 URL 清单抓正文（通用版，供 payoneer_olive 各平台复用）。

与 `bol_partner_portal_fetch.py` 的区别：那个是 Bol 专用（写死了页脚标记和导航切割规则），
这个吃一份 URL 清单、用通用规则抽正文，适配 eBay / Walmart / BestBuy 等站点。

正文抽取的通用做法（从 Bol 那次总结出来的）：
- 去掉 script/style/nav/footer/header 后取文本；
- **按 `<h1>~<h4>` 切小节**并用 `## 标题` 标记边界 —— 这条最关键：
  下游按小节切块，块的向量才代表该小节主题；按字符数盲切会让块向量代表开头那段，
  实测会让正确答案排到 680/2492 名开外、永远召不回。
- 正文过短（多为导航页/空壳）直接丢弃，不写盘。

产出 `<slug>.txt`（首行标题 + `## 小节` 正文）+ `manifest.json`，
可直接喂给 `build_crawl_manifest_from_text.py` → `run_local_mining.py`。
"""

import argparse
import html
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import requests

PROJECT_ROOT = str(_PROJECT_ROOT)

LOGGER = logging.getLogger(__name__)
_SPACE_RE = re.compile(r'\s+')

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}


def fetch(url: str, timeout: int = 30, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.text
            LOGGER.warning('HTTP %s %s', r.status_code, url)
            if r.status_code in (404, 410):
                return None
        except requests.RequestException as exc:
            LOGGER.warning('请求失败(%s/%s) %s: %s', attempt + 1, retries, url, exc)
        time.sleep(1.5 * (attempt + 1))
    return None


def _strip(raw: str) -> str:
    body = re.sub(r'(?s)<(script|style|noscript|nav|footer|header)\b.*?</\1>', ' ', raw)
    return body


def extract_title(raw: str) -> str:
    """取标题：<title> 优先，缺失时退回第一个 <h1>。

    有些站点（实测 export.ebay.com）的 <title> 是客户端渲染的，
    静态 HTML 里根本没有这个标签，只看 <title> 会得到 20/20 全空。
    """
    m = re.search(r'<title>(.*?)</title>', raw, re.S | re.I)
    if not m:
        m = re.search(r'(?is)<h1[^>]*>(.*?)</h1>', raw)
    if not m:
        return ''
    t = html.unescape(_SPACE_RE.sub(' ', re.sub(r'<[^>]+>', ' ', m.group(1)))).strip()
    # 去掉站点后缀：'Foo | eBay' / 'Foo - Walmart'
    return re.split(r'\s*[|｜]\s*', t)[0].strip()


# Cookie/隐私同意横幅：欧洲站点（Allegro/Cdiscount 等）几乎每页都有，
# 且常常排在第一个 <h> 小节 —— 实测 Allegro 30/30 篇首节都是它。
# 不剔掉的话每篇文档的第一个块都是这段，检索时会大面积召回噪声。
_CONSENT_RE = re.compile(
    r'(cookie|prywatno|privacy|consent|zgod|RODO|akceptuj|datenschutz|'
    r'confidentialit|vie priv|einwilligung)', re.I)


def extract_sections(raw: str) -> List[Tuple[str, str]]:
    """按 <h1>~<h4> 切 (小节标题, 小节正文)，剔除 cookie/隐私同意小节。"""
    body = _strip(raw)
    parts = re.split(r'(?is)<h([1-4])[^>]*>(.*?)</h\1>', body)
    out: List[Tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 3):
        head = _SPACE_RE.sub(' ', html.unescape(re.sub(r'<[^>]+>', ' ', parts[i + 1]))).strip()
        text = _SPACE_RE.sub(' ', html.unescape(re.sub(r'<[^>]+>', ' ', parts[i + 2]))).strip()
        if head and text and not _CONSENT_RE.search(head):
            out.append((head, text))
    return out


# 错误页：HTTP 200 但正文是 "404 / Page not found"。
# firecrawl 和裸 requests 都可能拿到这种页面，字数还不小（实测 ManoMano 的 404 页 1703 字、
# Lowes 1105 字），只按 min_chars 过滤会把它们当成有效语料落盘。
_ERROR_PAGE_RE = re.compile(
    r'(erreur\s*404|error\s*404|404\s*[-—:]?\s*(not found|page)|page not found|'
    r'页面不存在|页面未找到|seite nicht gefunden|página no encontrada)', re.I)


def looks_like_error_page(text: str) -> bool:
    """正文开头出现 404/未找到字样即判为错误页（只看开头，避免误伤正文里提到 404 的帮助页）。"""
    return bool(_ERROR_PAGE_RE.search(text[:600]))


def plain_text(raw: str) -> str:
    t = html.unescape(re.sub(r'<[^>]+>', ' ', _strip(raw)))
    return _SPACE_RE.sub(' ', t).strip()


def slug_of(url: str) -> str:
    s = re.sub(r'^https?://[^/]+/', '', url).strip('/')
    s = re.sub(r'[^a-zA-Z0-9\-_/]+', '-', s).replace('/', '_')
    return (s or 'index')[:120]


def crawl(urls: List[str], out_dir: str, workers: int = 5,
          min_chars: int = 300) -> Dict[str, dict]:
    os.makedirs(out_dir, exist_ok=True)
    results: Dict[str, dict] = {}

    def work(url: str) -> Tuple[str, Optional[str]]:
        return url, fetch(url)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, raw in pool.map(work, urls):
            if not raw:
                results[url] = {'ok': False, 'error': 'fetch_failed'}
                continue
            title = extract_title(raw)
            secs = extract_sections(raw)
            body = '\n\n'.join(f'## {h}\n{t}' for h, t in secs) if secs else plain_text(raw)
            slug = slug_of(url)
            rec = {'ok': True, 'url': url, 'slug': slug, 'title': title,
                   'chars': len(body), 'sections': len(secs)}
            if looks_like_error_page((title or '') + ' ' + body):
                rec['skipped_error_page'] = True
            elif len(body) >= min_chars:
                fp = os.path.join(out_dir, f'{slug}.txt')
                with open(fp, 'w', encoding='utf-8') as f:
                    f.write((title or slug) + '\n\n' + body + '\n')
                rec['file'] = fp
            else:
                rec['skipped_short'] = True
            results[url] = rec
    return results


def main():
    ap = argparse.ArgumentParser(description='按 URL 清单抓正文')
    ap.add_argument('--url-file', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--workers', type=int, default=5)
    ap.add_argument('--min-chars', type=int, default=300)
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--log-level', default='WARNING')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING),
                        format='%(asctime)s %(levelname)s %(message)s')

    urls = [l.strip() for l in open(args.url_file, encoding='utf-8') if l.strip()]
    if args.limit:
        urls = urls[:args.limit]
    print(f'待抓 {len(urls)} 个 URL → {args.out_dir}', flush=True)

    res = crawl(urls, args.out_dir, workers=args.workers, min_chars=args.min_chars)
    with open(os.path.join(args.out_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    ok = [r for r in res.values() if r.get('ok') and r.get('file')]
    short = [r for r in res.values() if r.get('skipped_short')]
    errpg = [r for r in res.values() if r.get('skipped_error_page')]
    failed = [r for r in res.values() if not r.get('ok')]
    print(f'成功落盘 {len(ok)} / 过短跳过 {len(short)} / '
          f'错误页跳过 {len(errpg)} / 失败 {len(failed)}')
    print(f"正文合计 {sum(r['chars'] for r in ok)} 字符")


if __name__ == '__main__':
    main()
