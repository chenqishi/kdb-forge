# crawl_single_page

## 所属文件
`knowledge_crawler_tool/web_crawl/single_page_local_crawl.py`

## 功能
抓取**单个** URL 并产出与 `web_batch_crawler.process_crawled_content_json_format` **完全同构**的
页面 JSON + TSV 映射文件，使得后续 `knowledge_translate_by_dify.py` / `knowledge_html_clear_by_dify.py` /
`quality_tools/qa_quality_tools.py` 可以原样复用，不需要跑 `html_kg_gen_task_control` 全链路。

## 为什么不用 web_batch_crawler
`WebBatchCrawler.__init__` 无条件 `setup_driver()` 并写死 `/usr/local/bin/chromedriver`，
本地 chromedriver 与 Chrome 大版本不一致时**连纯文本提取也起不来**；另外 Mercado
`vendedores.*/nota` 这类卖家页在 Selenium 下会卡住（见 `MEMORY.md`）。
本函数用 `requests` 直取 HTML，正文优先走 firecrawl（Dify workflow），完全不碰浏览器。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| url | str | 是 | - | 待抓取页面 URL |
| output_dir | str | 是 | - | 产物目录，不存在则创建 |
| client | str | 是 | - | 客户标识，写入 JSON 的 `client`；下游 QA 用它作 platform 兜底 |
| platform | str | 否 | `client` | TSV 第 0 列与 JSON 的 `platform` |
| content_type | str | 否 | `'normal'` | `normal` / `qa`；**为空会让下游 QA 阶段静默跳过该行** |
| category_name | str | 否 | `''` | 写入 JSON，QA 阶段会回填到每条 QA 上 |
| category_id | str | 否 | `''` | 同上 |
| flag | str | 否 | `'local'` | 产物文件名后缀（相当于 task_id） |
| use_firecrawl | bool | 否 | `True` | 是否调用 Dify firecrawl workflow 取正文 |
| user_agent | str | 否 | 桌面 Chrome UA | requests 请求头 UA |
| keep_attr_name | str/list | 否 | `'all'` | 生成文件名时保留哪些 query 参数 |
| timeout | int | 否 | `60` | requests 超时秒数 |
| cookie | str/dict | 否 | `None` | `"k=v; k2=v2"` 裸串或字典，**同时**用于 requests 取 HTML 和 firecrawl 取正文。多语言站点常靠 cookie 切语言（如 Wayfair 开发者门户 `DEV-PORTAL-LANGUAGE=zh-CN`） |
| wait_for | int | 否 | `0` | firecrawl 渲染等待毫秒，SPA 站点可调大 |

## Outputs
| 类型 | 说明 |
|------|------|
| str | TSV 映射文件路径 `<output_dir>/crawler_and_process_results_<flag>.txt` |

落盘文件（`<slug>` = `WebBatchCrawler.get_filename_from_url(url, keep_attr_name)`）：

- `<slug>.html` — requests 取回的原始 HTML（已存在则复用，与原管线一致）
- `<slug>.firecrawl.txt` — firecrawl 正文（已存在且非空则复用）
- `<slug>.json` — 页面 JSON，键与 stage2 逐字对齐：
  `platform, crawl_url, content_type, crawler_degree(=1), html_local_file, html_content,
   formatted_text, firecrawl_content_file, firecrawl_content, client, original_url,
   category_id, category_name`
- `crawler_and_process_results_<flag>.txt` — 单行 TSV，列序
  `platform \t crawl_url \t content_type \t crawler_degree \t html_local_file \t data_json_file`

## 逻辑说明
1. `WebBatchCrawler.get_filename_from_url`（静态调用）生成 slug
2. HTML：文件存在则读取复用，否则 `requests.get(..., allow_redirects=True)` 后 `raise_for_status()` 落盘
3. firecrawl：`DifyWorkFlowRequest(GLOBAL_CONFIG['dify_api_base'], GLOBAL_CONFIG['dify_api_key_firecrawl'])`
   `.request_dify("", other_inputs={"url": url})`；返回 `None` 只告警不落空文件
4. `formatted_text` 由 `WebBatchCrawler.extract_formatted_text_by_flat`（静态调用）生成
5. **正文非空校验**：`firecrawl_content` 与 `formatted_text` 同时为空 → 抛 `RuntimeError`。
   避免产出会被 `knowledge_html_clear_by_dify.py:146` 静默 `continue` 的半成品
6. 写 `<slug>.json` 与单行 TSV，返回 TSV 路径

## 依赖的外部接口
- **Firecrawl 官方 API**（2026-08-08 起）：`POST {firecrawl_api_base}/v2/scrape`，
  经 `commons/firecrawl_tools.fetch_firecrawl_content` 调用，token 取
  `GLOBAL_CONFIG['firecrawl_api_key']`。详见 `function_schema/firecrawl_tools.*.md`。
- ~~Dify workflow `POST {dify_api_base}/workflows/run`（key `dify_api_key_firecrawl`）~~ 已废弃：
  该 workflow 用的插件 `langgenius/firecrawl:0.0.3` 的 `headers` 参数已坏，任何非空 header
  都会 `status=succeeded` 却返回空串，导致 cookie 传不进去。

## SQL
无。
