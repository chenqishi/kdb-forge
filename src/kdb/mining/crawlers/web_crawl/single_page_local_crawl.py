#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
单页本地抓取：抓一个 URL，产出与 web_batch_crawler.process_crawled_content_json_format
完全同构的页面 JSON + TSV 映射，后续翻译 / QA 抽取 / 质量分级直接复用现有 CLI。

不走 Selenium：WebBatchCrawler.__init__ 会无条件起 chromedriver，本地版本不匹配时
连纯文本提取都起不来；且 Mercado vendedores/nota 这类卖家页在 Selenium 下会卡住。
正文优先取 firecrawl（Dify workflow），HTML 用 requests 直取。
"""

import json
import logging
import os
import sys
import time

import fire
import requests

from commons.firecrawl_tools import build_cookie_headers, fetch_firecrawl_content
from knowledge_crawler_tool.web_crawl.web_batch_crawler import WebBatchCrawler

DEFAULT_USER_AGENT = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')


def _fetch_html(url, html_local_file, user_agent, timeout, cookie=None):
    """取 HTML，已存在则复用（与 web_batch_crawler 的 skip crawl 行为一致）"""
    if os.path.exists(html_local_file) and os.path.getsize(html_local_file) > 0:
        logging.info(f'HTML 已存在，复用: {html_local_file}')
        with open(html_local_file, 'r', encoding='utf-8') as f:
            return f.read()

    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    }
    headers.update(build_cookie_headers(cookie))
    response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'
    html_content = response.text
    with open(html_local_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logging.info(f'HTML 抓取完成: {url} -> {html_local_file} ({len(html_content)} 字符)')
    return html_content


def _fetch_firecrawl(url, firecrawl_content_file, cookie=None, user_agent=None, wait_for=0):
    """直连 Firecrawl API 取正文，已存在且非空则复用；失败返回空串。

    原先走 Dify workflow，但那个 `langgenius/firecrawl:0.0.3` 插件的 headers 已坏
    （非空 header 就静默返回空串），cookie 传不进去，故改为直连。
    """
    if os.path.exists(firecrawl_content_file):
        with open(firecrawl_content_file, 'r', encoding='utf-8') as f:
            cached = f.read()
        if cached.strip():
            logging.info(f'firecrawl 正文已存在，复用: {firecrawl_content_file}')
            return cached

    firecrawl_content = fetch_firecrawl_content(url, cookie=cookie, user_agent=user_agent,
                                                wait_for=wait_for)
    if not firecrawl_content:
        logging.warning(f'firecrawl 未取到正文: {url}')
        return ''
    with open(firecrawl_content_file, 'w', encoding='utf-8') as f:
        f.write(firecrawl_content)
    logging.info(f'firecrawl 正文完成: {len(firecrawl_content)} 字符 -> {firecrawl_content_file}')
    return firecrawl_content


def crawl_single_page(url, output_dir, client, platform=None, content_type='normal',
                      category_name='', category_id='', flag='local', use_firecrawl=True,
                      user_agent=None, keep_attr_name='all', timeout=60,
                      cookie=None, wait_for=0):
    """
    抓取单个 URL，产出 stage2 同构的页面 JSON 与单行 TSV 映射文件。

    :param cookie: "k=v; k2=v2" 裸串或字典，同时用于 requests 取 HTML 和 firecrawl 取正文。
                   多语言站点常靠 cookie 切语言（如 Wayfair 开发者门户 DEV-PORTAL-LANGUAGE=zh-CN）
    :param wait_for: firecrawl 渲染等待毫秒，SPA 站点可调大
    :return: TSV 映射文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    platform = platform or client
    user_agent = user_agent or DEFAULT_USER_AGENT

    slug = WebBatchCrawler.get_filename_from_url(url, keep_attr_name=keep_attr_name)
    html_local_file = os.path.join(output_dir, f'{slug}.html')
    html_content = _fetch_html(url, html_local_file, user_agent, timeout, cookie=cookie)

    firecrawl_content_file = os.path.join(output_dir, f'{slug}.firecrawl.txt')
    firecrawl_content = _fetch_firecrawl(
        url, firecrawl_content_file, cookie=cookie, user_agent=user_agent,
        wait_for=wait_for) if use_firecrawl else ''

    formatted_text = WebBatchCrawler.extract_formatted_text_by_flat(html_local_file)

    if not firecrawl_content.strip() and not formatted_text.strip():
        raise RuntimeError(
            f'正文为空，firecrawl 与 formatted_text 都没抓到内容: {url}。'
            f'不产出半成品（下游 knowledge_html_clear_by_dify 会静默跳过空正文），请改用浏览器方案取正文。')

    result_dict = {
        'platform': platform,
        'crawl_url': url,
        'content_type': content_type,
        'crawler_degree': 1,
        'html_local_file': html_local_file,
        'html_content': html_content,
        'formatted_text': formatted_text,
        'client': client,
        'original_url': url,
    }
    if use_firecrawl and firecrawl_content:
        result_dict['firecrawl_content_file'] = firecrawl_content_file
        result_dict['firecrawl_content'] = firecrawl_content
    if category_id:
        result_dict['category_id'] = category_id
    if category_name:
        result_dict['category_name'] = category_name

    data_json_file = html_local_file.replace('.html', '.json')
    with open(data_json_file, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=4)

    process_url_info_file = os.path.join(output_dir, f'crawler_and_process_results_{flag}.txt')
    print_field = [platform, url, content_type, 1, html_local_file, data_json_file]
    with open(process_url_info_file, 'w', encoding='utf-8') as f:
        f.write('\t'.join(map(str, print_field)) + '\n')

    logging.info(f'单页抓取完成: formatted_text={len(formatted_text)} 字符, '
                 f'firecrawl_content={len(firecrawl_content)} 字符, 映射文件={process_url_info_file}')
    return process_url_info_file


def _load_json(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f'读取 JSON 失败 {path}: {e}')
        return {}


def export_local_qa_result(reclear_map_file, output_dir, flag='local', source_url=''):
    """
    把 *_qa_quality_re_clear.json 的 {high, mid, low} 拍平成人工可读的 QA 清单与 manifest。

    :return: 统计字典
    """
    os.makedirs(output_dir, exist_ok=True)
    qa_rows = []
    qa_count_by_level = {'high': 0, 'mid': 0, 'low': 0}
    char_stats = {'html_bytes': 0, 'formatted_text_chars': 0,
                  'firecrawl_chars': 0, 'translated_chars': 0}
    pages = []

    with open(reclear_map_file, 'r', encoding='utf-8') as f:
        for line in f:
            fields = line.strip().split('\t')
            if len(fields) < 2:
                continue
            crawl_url = fields[1]
            reclear_file = fields[-1]
            pages.append(crawl_url)
            if not source_url:
                source_url = crawl_url

            quality_result = _load_json(reclear_file)
            for level in ('high', 'mid', 'low'):
                for qa_item in quality_result.get(level, []) or []:
                    qa_count_by_level[level] = qa_count_by_level.get(level, 0) + 1
                    qa_rows.append({
                        'quality_level': level,
                        'q': qa_item.get('q', ''),
                        'a': qa_item.get('a', ''),
                        'from_file_name': qa_item.get('from_file_name', crawl_url),
                        'quality_info': qa_item.get('quality_info', []),
                        'category_name': qa_item.get('category_name', ''),
                        'original_url': qa_item.get('original_url', ''),
                    })

            # 字数统计：TSV 第 5 列是页面 JSON，同目录的 _trans.json 是翻译产物
            page_json_file = fields[5] if len(fields) > 5 else ''
            page_json = _load_json(page_json_file)
            char_stats['html_bytes'] += len(page_json.get('html_content', ''))
            char_stats['formatted_text_chars'] += len(page_json.get('formatted_text', ''))
            char_stats['firecrawl_chars'] += len(page_json.get('firecrawl_content', ''))
            trans_json = _load_json(f'{page_json_file}_trans.json')
            char_stats['translated_chars'] += len(trans_json.get('translated_text', ''))

    qa_result_file = os.path.join(output_dir, f'qa_result_{flag}.json')
    with open(qa_result_file, 'w', encoding='utf-8') as f:
        json.dump(qa_rows, f, ensure_ascii=False, indent=4)

    manifest_file = os.path.join(output_dir, f'manifest_{flag}.json')
    manifest = {
        'source_url': source_url,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'flag': flag,
        'pages': pages,
        'qa_count_by_level': qa_count_by_level,
        'qa_total': len(qa_rows),
        'char_stats': char_stats,
        'files': {
            'reclear_map_file': reclear_map_file,
            'qa_result_file': qa_result_file,
        },
    }
    with open(manifest_file, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=4)

    logging.info(f'QA 汇总完成: 共 {len(qa_rows)} 条 {qa_count_by_level} -> {qa_result_file}')
    return {
        'qa_result_file': qa_result_file,
        'manifest_file': manifest_file,
        'qa_count_by_level': qa_count_by_level,
        'qa_total': len(qa_rows),
    }


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    fire.Fire({
        'crawl_single_page': crawl_single_page,
        'export_local_qa_result': export_local_qa_result,
    })
