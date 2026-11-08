#!/usr/bin/env python
# -*- coding:utf8 -*-
"""抓取绿通官网（greenchannel.payoneer.com.cn）全部平台页，产出结构化知识。

## 为什么不走通用挖掘
这批页面是**强结构化**的：每个平台详情页固定 5 个板块
（入驻介绍 / 平台特点 / 热卖品类 / 平台数据 / 回款周期），
仓库里早有专用解析器 `knowledge_clear_tool/special_clear_method.py`
的 `get_green_channel_payonner_parse_data()` / `clear_greenchannel_payoneer_data()`，
2025-04 那批知识就是它产出的。本脚本只负责**把渲染后的 HTML 取下来**，
解析与 Dify 清洗仍复用既有方法，保证产出格式与历史一致。

## 页面是 OutSystems SPA，必须渲染
裸 requests 和 firecrawl 都只能拿到 2328 字节的空壳（"JavaScript is required"）。
用本机已有的 Chrome（playwright 缓存里的）`--headless --dump-dom` 渲染。
不新装依赖。

## 板块 id 映射（实测 2026-09-01）
    Intro_1 入驻介绍 / Intro_2 平台特点 / Intro_3 热卖品类
    Intro_4 平台数据 / Intro_5 回款周期
解析器里 `sections` 的 id 是空字符串（历史遗留），本脚本按上面映射补齐。
"""
import argparse
import html as _html
import json
import logging
import os
import re
import subprocess
import time

LOGGER = logging.getLogger(__name__)

CHROME = '/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'
BASE = 'https://greenchannel.payoneer.com.cn/GCPortal/'
CATALOG = BASE + 'PlatformCatalog'
DETAIL = BASE + 'PlatformDetail?PlatformId=%s'
SECTIONS = [('Intro_1', '入驻介绍'), ('Intro_2', '平台特点'), ('Intro_3', '热卖品类'),
            ('Intro_4', '平台数据'), ('Intro_5', '回款周期')]


def render(url, out_path, budget_ms=20000, timeout=120, retries=3):
    """用无头 Chrome 渲染页面并落盘 DOM。失败重试 + 退避。

    连续快速启动 Chrome 会被站点限流，返回 2261 字节的空壳（不是页面本身没内容）——
    实测同一个 id 单独重试就能拿到 4 万字节正常 DOM。所以必须重试而不是当失败跳过。
    """
    size = 0
    for attempt in range(retries):
        cmd = [CHROME, '--headless', '--disable-gpu', '--no-sandbox',
               '--virtual-time-budget=%d' % (budget_ms + attempt * 5000),
               '--dump-dom', url]
        try:
            with open(out_path, 'w', encoding='utf-8') as f:
                subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        size = os.path.getsize(out_path)
        if size > 10000:
            return True, size
        time.sleep(3 * (attempt + 1))       # 退避，缓解限流
    return False, size


def parse_catalog(html_path):
    """从目录页 DOM 抽 (platform_id, 平台名)。"""
    raw = open(html_path, encoding='utf-8').read()
    out = {}
    for m in re.finditer(r'PlatformDetail\?PlatformId=(\d+)', raw):
        pid = m.group(1)
        if pid in out:
            continue
        seg = raw[max(0, m.start() - 1200):m.end() + 400]
        names = [_html.unescape(re.sub(r'<[^>]+>', '', x)).strip()
                 for x in re.findall(r'>([^<>]{2,40})<', seg)]
        # 过滤掉「热门」「绿色通道」这类角标
        names = [n for n in names if n and n not in ('热门', '绿色通道', '新上线')
                 and not n.startswith(('http', '/', '{'))]
        if names:
            out[pid] = names[0]
    return out


def parse_detail(html_path):
    """按既有解析器的口径抽平台名与 5 个板块。返回 (platform, {板块名: html})。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(open(html_path, encoding='utf-8').read(), 'html.parser')
    node = soup.find('span', {'class': 'heading5'})
    platform = node.text.strip() if node else ''
    data = {}
    for sec_id, name in SECTIONS:
        d = soup.find('div', {'id': sec_id})
        if not d:
            continue
        hf = d.find('div', {'class': 'html-font'}) or d
        inner = hf.decode_contents().strip()
        text = hf.get_text().strip()
        if len(text) < 10:
            continue
        data[name] = {'html_content': inner, 'text_content': text}
    return platform, data


def main():
    ap = argparse.ArgumentParser(description='抓取绿通官网全部平台页')
    ap.add_argument('--out-dir', default='data/payoneer/greenchannel_%s' % time.strftime('%Y%m%d'))
    ap.add_argument('--only-ids', default='', help='逗号分隔的 PlatformId，默认全部')
    ap.add_argument('--extra-ids', default='',
                    help='目录页之外还要抓的 PlatformId（历史有、目录页已下架但页面仍在的）。'
                         '实测 id=8 美客多Mercado Libre 已从目录下架，但详情页仍有内容，'
                         '只爬目录会漏掉 11 个这类平台')
    ap.add_argument('--sleep', type=float, default=2.5)  # 调大：1.0 会触发站点限流
    ap.add_argument('--log-level', default='INFO')
    args = ap.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(message)s')

    os.makedirs(args.out_dir, exist_ok=True)
    cat_path = os.path.join(args.out_dir, '_catalog.html')
    ok, size = render(CATALOG, cat_path)
    if not ok:
        raise SystemExit('目录页渲染失败，仅 %d 字节' % size)
    plats = parse_catalog(cat_path)
    LOGGER.info('目录页解析到 %d 个平台', len(plats))
    for x in (i.strip() for i in args.extra_ids.split(',')):
        if x and x not in plats:
            plats[x] = '(目录页已下架)'
    if args.extra_ids:
        LOGGER.info('加上 --extra-ids 后共 %d 个待抓', len(plats))

    want = {x.strip() for x in args.only_ids.split(',') if x.strip()}
    manifest = {}
    for pid, name in sorted(plats.items(), key=lambda x: int(x[0])):
        if want and pid not in want:
            continue
        fp = os.path.join(args.out_dir, 'PlatformId_%s.html' % pid)
        try:
            ok, size = render(DETAIL % pid, fp)
        except subprocess.TimeoutExpired:
            LOGGER.warning('id=%s 渲染超时', pid); continue
        if not ok:
            LOGGER.warning('id=%s 渲染过短(%d)，跳过', pid, size); continue
        platform, data = parse_detail(fp)
        manifest[pid] = {'platform_id': pid, 'catalog_name': name,
                         'platform': platform or name,
                         'sections': {k: len(v['text_content']) for k, v in data.items()},
                         'html_file': fp}
        LOGGER.info('id=%-4s %-24s 板块 %s', pid, platform or name, list(data))
        time.sleep(args.sleep)

    mf = os.path.join(args.out_dir, 'manifest.json')
    json.dump(manifest, open(mf, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_sec = sum(len(v['sections']) for v in manifest.values())
    print('完成：%d 个平台，%d 个板块 → %s' % (len(manifest), n_sec, mf))


if __name__ == '__main__':
    main()
