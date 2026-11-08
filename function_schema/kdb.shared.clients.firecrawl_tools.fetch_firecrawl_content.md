# kdb.shared.clients.firecrawl_tools.fetch_firecrawl_content

## Signature

`fetch_firecrawl_content(url, cookie=None, user_agent=None, wait_for=DEFAULT_WAIT_FOR_MS, scraper=None, raise_on_error=False, min_content_length=DEFAULT_MIN_CONTENT_LENGTH)`

## 功能

模块级便捷函数：给 URL（可选 cookie）拿 markdown 正文。
这是给 `web_batch_crawler.py` / `single_page_local_crawl.py` 用的**统一入口**，
两处原本各自 `DifyWorkFlowRequest(...).request_dify('', other_inputs={'url': url})`，现在都改调它。

## Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| url | str | 是 | - | 目标页面 |
| cookie | str/dict | 否 | `None` | 经 `build_cookie_headers` 归一 |
| user_agent | str | 否 | `None` | 同上 |
| wait_for | int | 否 | `0` | 渲染等待毫秒；SPA 站点可调大 |
| scraper | FirecrawlScraper | 否 | `None` | 复用已有实例；`None` 时按模块单例懒加载 |
| raise_on_error | bool | 否 | `False` | `False` 时把异常降级成返回 `''` 并 `logging.error` |
| min_content_length | int | 否 | `400` | 正文短于该值当失败重试。**默认开启**，用来挡 firecrawl 的间歇性空返回，见 `firecrawl_tools.FirecrawlScraper.md` |

## Outputs

| 类型 | 说明 |
|------|------|
| str | markdown 正文；失败或抓空返回 `''` |

## 逻辑说明

1. `scraper` 为空 → 取模块单例 `_get_default_scraper()`（`FirecrawlScraper()`，缺 key 会抛 `ValueError`）
2. `build_cookie_headers(cookie, user_agent)` 得到 headers，空字典则不传
3. 调 `scraper.scrape(...)`
4. `raise_on_error=False` 时吞掉异常返回 `''`

## 调用方注意（这是踩过的坑）

**返回空串必须当失败处理**，不要写进 `.firecrawl.txt` 当成功缓存 ——
原 Dify 插件正是"succeeded + 空串"，而 `web_batch_crawler.py:346` 无条件把返回值写盘，
导致下游 `process_key='firecrawl_content'` 拿到空内容整页静默跳过、任务却显示成功。

## 依赖的外部接口

见 `firecrawl_tools.FirecrawlScraper.md`。

## SQL

无。

## Source

`src/kdb/shared/clients/firecrawl_tools.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
