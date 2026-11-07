# -*- coding: utf-8 -*-
"""直连 Firecrawl 官方 API 抓取单页正文，替代原来的 Dify firecrawl workflow。

原链路 `DifyWorkFlowRequest(api_key=GLOBAL_CONFIG['dify_api_key_firecrawl'])` 走的是
插件 `langgenius/firecrawl:0.0.3`，该版本 **`headers` 参数已坏**：任何非空 header
（哪怕只是 User-Agent）都让它 `status=succeeded` 却返回空串，于是 cookie 根本传不进去，
空串还会被当成正文写盘、下游整页静默跳过。

默认参数逐项对齐 `data/网页爬取url.yml` 里那个 workflow，换实现后产物形态不变。
详见 `function_schema/firecrawl_tools.*.md`。
"""

import logging

import requests

from config_tools.config import GLOBAL_CONFIG

DEFAULT_API_BASE = 'https://api.firecrawl.dev'
DEFAULT_API_VERSION = 'v2'
# 抄自 data/网页爬取url.yml 的 tool_configurations，勿随意改动
DEFAULT_FORMATS = ['markdown']
DEFAULT_ONLY_MAIN_CONTENT = True
DEFAULT_PAGE_TIMEOUT_MS = 30000
DEFAULT_WAIT_FOR_MS = 0
# firecrawl 会间歇性返回只剩 cookie 横幅/路径的近乎空内容却 success=true
# （实测同一 URL 批量跑返回 26 字符、单独重试返回 12518 字符，与 waitFor 无关）。
# 400 字符足以放过合法短页，又能挡住这类"只剩样板"的空返回。
DEFAULT_MIN_CONTENT_LENGTH = 400


def build_cookie_headers(cookie=None, user_agent=None, extra_headers=None):
    """把仓库里的 cookie 裸串/字典归一成 Firecrawl 的 headers 字典。

    `auth_config['cookie']` 一直是 "k=v; k2=v2" 裸串，而 Firecrawl 要 {"Cookie": "..."}。
    """
    headers = {}

    if isinstance(cookie, dict):
        # 已经是 headers 字典就原样用，别再包一层
        if any(key.lower() == 'cookie' for key in cookie):
            headers.update(cookie)
        elif cookie:
            headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in cookie.items())
    elif isinstance(cookie, str) and cookie.strip():
        headers['Cookie'] = cookie.strip()

    if user_agent:
        headers['User-Agent'] = user_agent
    if extra_headers:
        headers.update(extra_headers)
    return headers


class FirecrawlScraper:
    """Firecrawl scrape API 客户端。"""

    def __init__(self, api_key=None, api_base=None, api_version=DEFAULT_API_VERSION,
                 max_retries=3, timeout=180):
        self.api_key = api_key or GLOBAL_CONFIG.get('firecrawl_api_key')
        if not self.api_key:
            raise ValueError(
                'firecrawl_api_key 未配置。请在 config/global_config.json 中设置 '
                '"firecrawl_api_key"（该文件已 gitignore，不要把 token 写进代码）')
        self.api_base = (api_base or GLOBAL_CONFIG.get('firecrawl_api_base')
                         or DEFAULT_API_BASE).rstrip('/')
        self.api_version = api_version
        self.max_retries = max_retries
        self.timeout = timeout

    @property
    def scrape_url(self):
        return f'{self.api_base}/{self.api_version}/scrape'

    def scrape(self, url, headers=None, formats=None, only_main_content=DEFAULT_ONLY_MAIN_CONTENT,
               wait_for=DEFAULT_WAIT_FOR_MS, page_timeout=DEFAULT_PAGE_TIMEOUT_MS,
               include_tags=None, exclude_tags=None, min_content_length=0):
        """抓一个页面，返回 markdown 正文；抓不到返回空串。

        min_content_length: 正文短于该值就当失败重试。**强烈建议设**——firecrawl 会
        间歇性返回只剩 cookie 横幅/路径的近乎空内容却 `success=true`（实测同一 URL
        批量跑返回 26 字符、单独重试返回 12518 字符，与 waitFor 无关）。
        """
        if isinstance(headers, str):
            headers = build_cookie_headers(headers)

        payload = {
            'url': url,
            'formats': formats or DEFAULT_FORMATS,
            'onlyMainContent': only_main_content,
            'timeout': page_timeout,
            'waitFor': wait_for,
        }
        if headers:
            payload['headers'] = headers
        if include_tags:
            payload['includeTags'] = include_tags
        if exclude_tags:
            payload['excludeTags'] = exclude_tags

        request_headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(self.scrape_url, headers=request_headers,
                                         json=payload, timeout=self.timeout)
                if response.status_code != 200:
                    last_error = f'HTTP {response.status_code}: {response.text[:300]}'
                    logging.warning(
                        f'firecrawl scrape 第 {attempt}/{self.max_retries} 次失败: {last_error}')
                    continue

                result = response.json()
                if not result.get('success'):
                    last_error = f'success=false: {str(result.get("error"))[:300]}'
                    logging.warning(
                        f'firecrawl scrape 第 {attempt}/{self.max_retries} 次失败: {last_error}')
                    continue

                markdown = (result.get('data') or {}).get('markdown') or ''
                if min_content_length and len(markdown) < min_content_length:
                    # 这个"成功但内容近乎为空"是间歇性的，重试通常就好了
                    last_error = (f'正文过短 {len(markdown)} < {min_content_length}，'
                                  f'疑似 firecrawl 间歇性空返回')
                    logging.warning(
                        f'firecrawl scrape 第 {attempt}/{self.max_retries} 次: {last_error} ({url})')
                    continue
                if not markdown:
                    logging.warning(f'firecrawl 返回空正文: {url}')
                return markdown
            except Exception as exc:
                last_error = f'{type(exc).__name__}: {exc}'
                logging.warning(
                    f'firecrawl scrape 第 {attempt}/{self.max_retries} 次异常: {last_error}')

        raise RuntimeError(f'firecrawl scrape 失败（已重试 {self.max_retries} 次）: {url}, {last_error}')


_DEFAULT_SCRAPER = None


def _get_default_scraper():
    global _DEFAULT_SCRAPER
    if _DEFAULT_SCRAPER is None:
        _DEFAULT_SCRAPER = FirecrawlScraper()
    return _DEFAULT_SCRAPER


def fetch_firecrawl_content(url, cookie=None, user_agent=None, wait_for=DEFAULT_WAIT_FOR_MS,
                            scraper=None, raise_on_error=False,
                            min_content_length=DEFAULT_MIN_CONTENT_LENGTH):
    """给 URL（可选 cookie）拿 markdown 正文。爬虫侧的统一入口。

    注意：返回空串一律当失败处理，别写盘当成功缓存——原 Dify 插件就是"成功+空串"，
    空正文写进 .firecrawl.txt 会让下游整页静默跳过而任务显示成功。
    """
    try:
        scraper = scraper or _get_default_scraper()
        headers = build_cookie_headers(cookie, user_agent)
        return scraper.scrape(url, headers=headers or None, wait_for=wait_for,
                              min_content_length=min_content_length)
    except Exception as exc:
        if raise_on_error:
            raise
        logging.error(f'firecrawl 取正文失败: {url}, {type(exc).__name__}: {exc}')
        return ''
