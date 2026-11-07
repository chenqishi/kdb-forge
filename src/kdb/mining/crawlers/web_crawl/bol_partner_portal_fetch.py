from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Bol 卖家帮助中心（partnerplatform.bol.com）正文抓取。

用途：为 payoneer_olive 知识库补 Bol 平台的缺口知识（见
`/root/sell_agents/docs/payoneer_olive_kb_gap_tasks_20260829.md`）。

为什么单独写一个而不是用 web_batch_crawler：
- 这个站不需要 JS 渲染，静态 HTML 里就有正文，`requests` 足够，不用起浏览器、
  也不用 firecrawl（本项目没配 firecrawl key）。
- 站点结构是**两层**：`/en/idp/xxx` 里有一部分是「索引页」（只有一句导语 +
  一组子链接），真正的正文在子页。一次性把两层都抓下来，避免只拿到索引页。

正文抽取要点（这个站的具体形态）：
- 每页 HTML 约 260KB，但其中绝大部分是全站导航（顶部菜单把所有栏目都列了一遍），
  纯文本抽出来约 6000 字符里只有最后一两千字是正文。
- 正文起点：标题会连续重复 2~4 次（模板渲染面包屑+H1+标题块），取**最后一次出现**之后。
- 正文终点：页脚固定以 `Categories Offer Orders & Shipping` 开头。

产出：`data/payoneer_olive/Bol/<slug>.txt`（首行标题 + 正文）+ `manifest.json`。
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
from typing import Dict, List, Optional, Tuple

import requests

PROJECT_ROOT = str(_PROJECT_ROOT)

BASE = 'https://partnerplatform.bol.com'
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, 'data', 'payoneer_olive', 'Bol')

_SPACE_RE = re.compile(r'\s+')

# 页脚起点，正文到此为止
_FOOTER_MARK = 'Categories Offer'
# 站点导航里出现的固定串，用于判断是不是只抓到了导航
_NAV_TAIL = 'Start selling via bol Menu'

_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'),
    'Accept-Language': 'en',
}


def fetch_html(url: str, timeout: int = 30, retries: int = 3) -> Optional[str]:
    """取 HTML，失败重试。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            logging.warning('HTTP %s %s', resp.status_code, url)
        except requests.RequestException as exc:
            logging.warning('请求失败(%s/%s) %s: %s', attempt + 1, retries, url, exc)
        time.sleep(1.5 * (attempt + 1))
    return None


def html_to_text(raw: str) -> str:
    """HTML → 纯文本（去 script/style，压空白）。"""
    body = re.sub(r'(?s)<(script|style|noscript)\b.*?</\1>', ' ', raw)
    text = html.unescape(re.sub(r'<[^>]+>', ' ', body))
    return re.sub(r'\s+', ' ', text).strip()


def extract_title(raw: str) -> str:
    """取 <title>，去掉站点后缀。"""
    m = re.search(r'<title>(.*?)</title>', raw, re.S | re.I)
    if not m:
        return ''
    title = html.unescape(re.sub(r'\s+', ' ', m.group(1))).strip()
    return title.split('|')[0].strip()


def extract_article(raw: str) -> Tuple[str, str]:
    """从整页文本里切出正文。

    Returns:
        (title, body)；切不出正文时 body 为空串。
    """
    title = extract_title(raw)
    text = html_to_text(raw)

    # 先砍页脚
    idx = text.find(_FOOTER_MARK)
    if idx > 0:
        text = text[:idx]

    body = text
    if title:
        # 标题在模板里会重复出现，正文从最后一次出现之后开始
        last = text.rfind(title)
        if last >= 0:
            body = text[last + len(title):]

    # 还残留导航尾巴的话再切一次
    nav = body.find(_NAV_TAIL)
    if nav >= 0:
        body = body[nav + len(_NAV_TAIL):]

    return title, body.strip()


def extract_sections(raw: str) -> List[Tuple[str, str]]:
    """按 <h1>~<h4> 把正文切成 (小节标题, 小节正文)。

    为什么必须按标题切而不是按字符数盲切：盲切会把不同主题混进同一块，
    导致该块的向量代表的是块**开头**那段话，而不是块里真正的答案。
    实测：`selling-via-bol-as-an-eu-partner` 里回答「一次没成功能否补资料」的关键句
    （"we will not proceed this time. You are always welcome to try again next year."）
    被切进了一个以营销话术 "Personal collaboration: direct contact with colleagues..."
    开头的 900 字符块，向量相似度只有 0.4451、排名 680/2492，粗召回永远够不到。
    按 <h2> 切之后这句话落在 "Want to become a partner?" 小节里，标题即主题。
    """
    body = re.sub(r'(?s)<(script|style|noscript)\b.*?</\1>', ' ', raw)
    # 页脚之后不要
    cut = body.find('>Categories<')
    if cut > 0:
        body = body[:cut]

    parts = re.split(r'(?is)<h([1-4])[^>]*>(.*?)</h\1>', body)
    # parts: [前导, level, 标题, 正文, level, 标题, 正文, ...]
    sections: List[Tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 3):
        heading = html.unescape(re.sub(r'<[^>]+>', ' ', parts[i + 1]))
        heading = _SPACE_RE.sub(' ', heading).strip()
        chunk = parts[i + 2] if i + 2 < len(parts) else ''
        text = html.unescape(re.sub(r'<[^>]+>', ' ', chunk))
        text = _SPACE_RE.sub(' ', text).strip()
        if heading and text:
            sections.append((heading, text))
    return sections


def extract_links(raw: str) -> List[str]:
    """抽站内文章链接（/en/idp/ 与 /en/cdp/）。"""
    found = re.findall(r'href="(/en/(?:idp|cdp)/[^"#?]*)"', raw)
    out, seen = [], set()
    for path in found:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def crawl(slugs: List[str], out_dir: str, workers: int = 4,
          min_chars: int = 200, follow_depth: int = 1) -> Dict[str, dict]:
    """抓取 slug 列表，并按需向下跟进一层子链接。

    Args:
        slugs: 形如 `/en/idp/xxx` 的路径列表
        min_chars: 正文短于此值视为「索引页/空页」，只用于统计与跟进判断
        follow_depth: 再往下跟进几层子链接（这个站 1 层足够）
    """
    os.makedirs(out_dir, exist_ok=True)
    results: Dict[str, dict] = {}
    pending = list(dict.fromkeys(slugs))
    seen = set(pending)

    for depth in range(follow_depth + 1):
        if not pending:
            break
        logging.info('第 %s 层：待抓 %s 个', depth, len(pending))

        def work(path: str) -> Tuple[str, Optional[str]]:
            return path, fetch_html(BASE + path)

        next_round: List[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for path, raw in pool.map(work, pending):
                if not raw:
                    results[path] = {'ok': False, 'error': 'fetch_failed'}
                    continue
                title, body = extract_article(raw)
                slug = path.rstrip('/').split('/')[-1]
                rec = {
                    'ok': True,
                    'url': BASE + path,
                    'slug': slug,
                    'title': title,
                    'chars': len(body),
                    'is_index_like': len(body) < min_chars,
                    'depth': depth,
                }
                if body:
                    fp = os.path.join(out_dir, f'{slug}.txt')
                    sections = extract_sections(raw)
                    with open(fp, 'w', encoding='utf-8') as f:
                        f.write((title or slug) + '\n\n')
                        if sections:
                            # 用 '## ' 标记小节边界，供下游按小节切块
                            for head, text in sections:
                                f.write(f'## {head}\n{text}\n\n')
                        else:
                            f.write(body + '\n')
                    rec['file'] = fp
                    rec['sections'] = len(sections)
                results[path] = rec

                # 索引页/短页：把它的子链接加进下一轮
                if depth < follow_depth and rec['is_index_like']:
                    for child in extract_links(raw):
                        if child not in seen:
                            seen.add(child)
                            next_round.append(child)

        pending = next_round

    return results


def main():
    parser = argparse.ArgumentParser(description='抓取 Bol 卖家帮助中心正文')
    parser.add_argument('--slug-file', default=None,
                        help='每行一个 /en/idp/xxx 路径；不给则从首页自动发现')
    parser.add_argument('--out-dir', default=DEFAULT_OUT_DIR)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--follow-depth', type=int, default=1,
                        help='索引页再往下跟进几层，默认 1')
    parser.add_argument('--min-chars', type=int, default=200,
                        help='正文短于此值视为索引页')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    if args.slug_file:
        slugs = [l.strip() for l in open(args.slug_file, encoding='utf-8') if l.strip()]
    else:
        logging.info('未给 slug 文件，从首页发现文章链接')
        home = fetch_html(BASE + '/en/')
        if not home:
            raise SystemExit('首页抓取失败')
        slugs = extract_links(home)
    logging.info('种子 %s 个', len(slugs))

    results = crawl(slugs, args.out_dir, workers=args.workers,
                    min_chars=args.min_chars, follow_depth=args.follow_depth)

    ok = [r for r in results.values() if r.get('ok')]
    substantive = [r for r in ok if not r.get('is_index_like')]
    manifest = os.path.join(args.out_dir, 'manifest.json')
    with open(manifest, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_chars = sum(r.get('chars', 0) for r in substantive)
    print(f'抓取 {len(results)} 个页面：成功 {len(ok)}，有实质正文 {len(substantive)}，'
          f'正文合计 {total_chars} 字符')
    print(f'manifest: {manifest}')
    print(f'输出目录: {args.out_dir}')


if __name__ == '__main__':
    main()
