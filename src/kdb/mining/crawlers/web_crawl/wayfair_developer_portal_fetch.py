#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Wayfair 开发者门户内容抓取（中文/英文）。

门户 https://developer.wayfair.io 是 Next.js 静态导出，正文全部由前端向内容 BFF 拉取，
且**没有中文 URL** —— 语言只由 cookie `DEV-PORTAL-LANGUAGE` 决定，切换后 URL 不变。
所以浏览器抓取意义不大，本模块直接调门户自己的内容 API 取指定 locale 的正文。

详见 `docs/wayfair_developer_zh_content_20260807.md` 与
`knowledge_crawler_tool/web_crawl/function_schema/wayfair_developer_portal_fetch.*.md`。
"""

import html
import json
import logging
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urlparse

import fire
import openpyxl

from knowledge_crawler_tool.web_crawl.web_batch_crawler import WebBatchCrawler

# 内容 BFF。同域的 public/ 与 v1/ 端点分别返回 403 / 401，只有 content/ 开放且免鉴权。
CONTENT_BFF_URL = 'https://api.wayfair.io/content/v1/developer-portal-bff/graphql'
PORTAL_ORIGIN = 'https://developer.wayfair.io'
DEFAULT_BUCKET_NAME = 'wf-developer-portal-prod'
DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/126.0 Safari/537.36'
)

# 两条 query 与门户前端 bundle 中的定义逐字一致，字段集合不可随意增删
POST_QUERY = '''query Post($slug: String!, $locale: String) {
  postCollection(where: {slug: $slug}, locale: $locale, limit: 1) {
    items {
      title
      body {
        json
        links {
          assets {
            block {
              sys { id }
              contentType
              url
            }
          }
        }
      }
      sys { id }
    }
  }
}'''

REFERENCE_QUERY = (
    'query ReferenceHtml($where: ReferenceFilter!) { referenceHtml(where: $where) }'
)

CJK_PATTERN = re.compile(r'[一-鿿]')

HEADING_NODES = {
    'heading-1': 'h1', 'heading-2': 'h2', 'heading-3': 'h3',
    'heading-4': 'h4', 'heading-5': 'h5', 'heading-6': 'h6',
}
# nodeType -> 包裹标签，正文实测节点集合是封闭的
SIMPLE_BLOCK_NODES = {
    'paragraph': 'p',
    'unordered-list': 'ul',
    'ordered-list': 'ol',
    'list-item': 'li',
    'table': 'table',
    'table-row': 'tr',
    'table-cell': 'td',
    'table-header-cell': 'th',
    'blockquote': 'blockquote',
}
# 固定顺序，保证多 mark 时输出稳定
MARK_TAGS = [('code', 'code'), ('bold', 'strong'), ('italic', 'em'), ('underline', 'u')]


def extract_urls_from_excel(excel_path, sheet_name=None):
    """提取单元格超链接目标。URL 存在 cell.hyperlink.target 上，不是 cell.value。"""
    workbook = openpyxl.load_workbook(excel_path)
    sheet_names = [sheet_name] if sheet_name else workbook.sheetnames

    url_infos = []
    for name in sheet_names:
        worksheet = workbook[name]
        for row in worksheet.iter_rows():
            for cell in row:
                if not cell.hyperlink or not cell.hyperlink.target:
                    continue
                label = str(cell.value).strip() if cell.value is not None else ''
                url_infos.append({
                    'label': label,
                    'url': cell.hyperlink.target.strip(),
                    'cell': cell.coordinate,
                    'sheet': name,
                })
    logging.info(f'extract_urls_from_excel: {excel_path} -> {len(url_infos)} urls')
    return url_infos


def parse_post_url(url):
    """把门户 URL 解析成内容 API 的取数参数。判定依据与前端 pages/posts/[...slug] 一致。"""
    parts = [seg for seg in urlparse(url).path.split('/') if seg]
    if 'posts' not in parts:
        raise ValueError(f'not a developer portal post url: {url}')

    slug_parts = parts[parts.index('posts') + 1:]
    if not slug_parts:
        raise ValueError(f'missing slug in url: {url}')

    if slug_parts[0] != 'docs':
        return {'kind': 'post', 'slug': slug_parts[0], 'url': url}

    if len(slug_parts) < 5:
        raise ValueError(f'incomplete reference url: {url}')
    return {
        'kind': 'reference',
        'api_id': slug_parts[1],
        'api_protocol': slug_parts[3],
        'version': slug_parts[4],
        'url': url,
    }


def graphql_post(query, variables, retries=3, timeout=90, backoff=2.0):
    """向内容 BFF 发 GraphQL 请求。并发时偶发 504，重试是必须的。"""
    payload = json.dumps({'query': query, 'variables': variables}).encode('utf-8')
    headers = {
        'content-type': 'application/json',
        'origin': PORTAL_ORIGIN,
        'referer': PORTAL_ORIGIN + '/',
        'user-agent': DEFAULT_USER_AGENT,
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(CONTENT_BFF_URL, data=payload, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
        except Exception as exc:
            last_error = exc
            logging.warning(f'graphql_post attempt {attempt}/{retries} failed: {exc}')
            if attempt < retries:
                time.sleep(backoff * attempt)
            continue

        if result.get('errors'):
            raise RuntimeError(f'graphql errors: {result["errors"]}')
        return result

    raise RuntimeError(f'graphql_post failed after {retries} attempts: {last_error}')


def fetch_post(slug, locale='zh-CN'):
    """取一篇 Post 的标题 + rich text 正文 JSON + 内嵌资源清单。"""
    result = graphql_post(POST_QUERY, {'slug': slug, 'locale': locale})
    items = ((result.get('data') or {}).get('postCollection') or {}).get('items') or []
    if not items:
        raise LookupError(f'no post content for slug={slug} locale={locale}')

    item = items[0]
    body = item.get('body') or {}
    assets = ((body.get('links') or {}).get('assets') or {}).get('block') or []
    return {
        'title': item.get('title') or slug,
        'body_json': body.get('json') or {},
        'assets': assets,
        'sys_id': (item.get('sys') or {}).get('id', ''),
    }


def fetch_reference_html(api_id, api_protocol='GraphQL', version='v1.0.0',
                         locale='zh-CN', bucket_name=DEFAULT_BUCKET_NAME):
    """取 API Reference 页 HTML。非 en-US 时 apiId 要拼 locale 后缀（前端同逻辑）。"""
    localized_api_id = api_id if locale == 'en-US' else f'{api_id}-{locale}'
    variables = {'where': {
        'bucketName': bucket_name,
        'apiProtocol': api_protocol,
        'apiId': localized_api_id,
        'version': version,
    }}
    result = graphql_post(REFERENCE_QUERY, variables)
    reference_html = (result.get('data') or {}).get('referenceHtml')
    if not reference_html:
        raise LookupError(
            f'no reference html for apiId={localized_api_id} version={version}')
    return reference_html


def _render_asset(node, asset_map):
    target_id = (((node.get('data') or {}).get('target') or {}).get('sys') or {}).get('id')
    asset = asset_map.get(target_id)
    if not asset:
        logging.warning(f'embedded asset not found in links: {target_id}')
        return f'<!-- missing asset: {html.escape(str(target_id))} -->'

    url = html.escape(asset.get('url') or '', quote=True)
    content_type = asset.get('contentType') or ''
    escaped_type = html.escape(content_type, quote=True)
    if content_type.startswith('image/'):
        return f'<img src="{url}" />'
    if content_type.startswith('video/'):
        return (f'<video controls><source src="{url}" type="{escaped_type}" /></video>')
    return f'<a href="{url}">{url}</a>'


def _render_node(node, asset_map):
    node_type = node.get('nodeType')

    if node_type == 'text':
        rendered = html.escape(node.get('value') or '')
        mark_types = {mark.get('type') for mark in (node.get('marks') or [])}
        for mark_type, tag in MARK_TAGS:
            if mark_type in mark_types:
                rendered = f'<{tag}>{rendered}</{tag}>'
        return rendered

    if node_type == 'hr':
        return '<hr />'

    if node_type == 'embedded-asset-block':
        return _render_asset(node, asset_map)

    children = ''.join(
        _render_node(child, asset_map) for child in (node.get('content') or []))

    if node_type == 'document':
        return children

    if node_type == 'hyperlink':
        uri = html.escape((node.get('data') or {}).get('uri') or '', quote=True)
        return f'<a href="{uri}">{children}</a>'

    tag = HEADING_NODES.get(node_type) or SIMPLE_BLOCK_NODES.get(node_type)
    if tag:
        return f'<{tag}>{children}</{tag}>'

    # 不静默丢内容：Contentful 以后新增节点类型时仍保留正文
    logging.warning(f'unknown rich text nodeType: {node_type}')
    escaped_type = html.escape(str(node_type), quote=True)
    return f'<div data-unknown-node="{escaped_type}">{children}</div>'


def richtext_to_html(body_json, assets=None):
    """Contentful Rich Text 文档 JSON -> HTML 片段。纯函数，无网络。"""
    asset_map = {
        (asset.get('sys') or {}).get('id'): asset
        for asset in (assets or [])
        if (asset.get('sys') or {}).get('id')
    }
    if not body_json:
        return ''

    top_nodes = body_json.get('content') or []
    if body_json.get('nodeType') != 'document':
        return _render_node(body_json, asset_map)
    return '\n'.join(_render_node(node, asset_map) for node in top_nodes)


def build_html_document(title, source_url, locale, inner_html, fetched_at=None):
    """包成完整 HTML 文档。<body> 是硬要求，下游 extract_formatted_text_by_flat 依赖它。"""
    fetched_at = fetched_at or datetime.now().isoformat(timespec='seconds')
    escaped_title = html.escape(title or '')
    escaped_url = html.escape(source_url or '', quote=True)
    return (
        '<!DOCTYPE html>\n'
        f'<html lang="{html.escape(locale, quote=True)}">\n'
        '<head>\n'
        '<meta charset="utf-8" />\n'
        f'<title>{escaped_title}</title>\n'
        f'<link rel="canonical" href="{escaped_url}" />\n'
        f'<!-- source_url: {escaped_url}\n'
        f'     locale: {html.escape(locale)}\n'
        f'     fetched_at: {html.escape(fetched_at)} -->\n'
        '</head>\n'
        '<body>\n'
        f'<h1>{escaped_title}</h1>\n'
        f'{inner_html}\n'
        '</body>\n'
        '</html>\n'
    )


def _extract_html_title(raw_html, fallback):
    match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.S | re.I)
    return match.group(1).strip() if match else fallback


def _is_full_html_document(raw_html):
    """判断是否已是完整 HTML 文档。

    不能用 `'<body' in raw_html` 这种子串判断：SpectaQL 生成的 reference 页会在每个代码示例里
    内嵌 `<html><head></head><body><pre><code>…`（实测 orders-api 有 52 处）。子串判断会把片段
    误判成完整文档而不加包装，随后 html.parser 遇到第一个内嵌 `<body>` 就把它之前的正文全部
    归到 head 下，`extract_formatted_text_by_flat` 只能抽到尾巴，正文静默丢失。

    真正的完整文档一定以 doctype 或 <html> 开头；片段以 <style> 开头。
    """
    head = re.sub(r'^(?:\s|<!--.*?-->)*', '', raw_html, flags=re.S).lower()
    return head.startswith('<!doctype') or head.startswith('<html')


def _fetch_one(url_info, output_dir, locale, overwrite):
    url = url_info['url']
    record = {
        'label': url_info.get('label', ''),
        'url': url,
        'kind': None,
        'slug': None,
        'file': None,
        'locale': locale,
        'title': None,
        'html_len': 0,
        'cjk_char_count': 0,
        'status': 'failed',
        'error': None,
    }

    try:
        parsed = parse_post_url(url)
        slug = WebBatchCrawler.get_filename_from_url(url)
        file_path = os.path.join(output_dir, f'{slug}.html')
        record['kind'] = parsed['kind']
        record['slug'] = slug
        record['file'] = file_path

        if not overwrite and os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as handle:
                page_html = handle.read()
            record['title'] = _extract_html_title(page_html, slug)
            logging.info(f'skip existing: {file_path}')
        else:
            if parsed['kind'] == 'post':
                post = fetch_post(parsed['slug'], locale=locale)
                inner_html = richtext_to_html(post['body_json'], post['assets'])
                page_html = build_html_document(post['title'], url, locale, inner_html)
                record['title'] = post['title']
            else:
                reference_html = fetch_reference_html(
                    parsed['api_id'], parsed['api_protocol'], parsed['version'],
                    locale=locale)
                title = _extract_html_title(reference_html, parsed['api_id'])
                record['title'] = title
                # 部分 reference 返回的是以 <style> 开头的片段，缺 <body> 下游会整页丢内容
                if _is_full_html_document(reference_html):
                    page_html = reference_html
                else:
                    page_html = build_html_document(title, url, locale, reference_html)

            with open(file_path, 'w', encoding='utf-8') as handle:
                handle.write(page_html)

        record['html_len'] = len(page_html)
        record['cjk_char_count'] = len(CJK_PATTERN.findall(page_html))
        record['status'] = 'ok'
        logging.info(
            f'ok {parsed["kind"]:9} {slug} len={record["html_len"]} '
            f'cjk={record["cjk_char_count"]}')
    except Exception as exc:
        record['error'] = f'{type(exc).__name__}: {exc}'
        logging.error(f'failed {url}: {record["error"]}')

    return record


def run_fetch(excel_path, output_dir, locale='zh-CN', flag=None, sheet_name=None,
              overwrite=True, max_workers=4):
    """入口：Excel URL 清单 -> 指定 locale 的 HTML 落盘 -> manifest。"""
    flag = flag or datetime.now().strftime('%Y%m%d')
    os.makedirs(output_dir, exist_ok=True)

    url_infos = extract_urls_from_excel(excel_path, sheet_name=sheet_name)
    seen_urls = set()
    unique_url_infos = []
    for url_info in url_infos:
        if url_info['url'] in seen_urls:
            logging.info(f'duplicate url skipped: {url_info["url"]}')
            continue
        seen_urls.add(url_info['url'])
        unique_url_infos.append(url_info)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        records = list(executor.map(
            lambda info: _fetch_one(info, output_dir, locale, overwrite),
            unique_url_infos))

    ok_count = sum(1 for record in records if record['status'] == 'ok')
    manifest = {
        'excel_path': excel_path,
        'locale': locale,
        'flag': flag,
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'total': len(records),
        'ok': ok_count,
        'failed': len(records) - ok_count,
        'items': records,
    }

    locale_tag = locale.replace('-', '').lower()
    manifest_path = os.path.join(
        output_dir, f'manifest_wayfair_dev_{locale_tag}_{flag}.json')
    with open(manifest_path, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    logging.info(f'total={manifest["total"]} ok={ok_count} failed={manifest["failed"]}')
    for record in records:
        if record['status'] != 'ok':
            logging.error(f'FAILED {record["url"]}: {record["error"]}')
        elif locale != 'en-US' and record['cjk_char_count'] == 0:
            logging.error(f'NO CHINESE CONTENT {record["url"]}')
    logging.info(f'manifest: {manifest_path}')
    return manifest_path


if __name__ == '__main__':
    # force=True 是必须的：import 链里已经有模块给 root logger 挂了 handler，
    # 不加就变成 no-op，level 停在 WARNING，逐条抓取进度全部看不到
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(filename)s:%(lineno)d]: %(message)s',
        force=True,
    )
    fire.Fire({
        'run_fetch': run_fetch,
        'extract_urls_from_excel': extract_urls_from_excel,
    })
