# run_fetch

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
Fire 入口。从 Excel 读 URL 清单 → 逐条按类型取指定 locale 的内容 → 落 HTML → 写 manifest。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| excel_path | str | 是 | - | URL 清单 xlsx |
| output_dir | str | 是 | - | HTML 落盘目录，不存在则创建 |
| locale | str | 否 | `'zh-CN'` | `zh-CN` / `en-US` |
| flag | str | 否 | 当天 `YYYYMMDD` | manifest 文件名后缀 |
| sheet_name | str | 否 | `None` | 传给 `extract_urls_from_excel` |
| overwrite | bool | 否 | `True` | `False` 时已存在的 `.html` 跳过不重取 |
| max_workers | int | 否 | `4` | 并发线程数；实测 8 并发会触发偶发 504，4 稳定 |

## Outputs
| 类型 | 说明 |
|------|------|
| str | manifest 路径 |

落盘：

- `<output_dir>/<slug>.html`，`<slug>` = `WebBatchCrawler.get_filename_from_url(url)`
  （复用 `web_batch_crawler.py` 的静态方法，与既有爬虫产物、ES `ext_info.from_file_name` 命名一致）
  - `.../posts/introduction` → `developer_wayfair_io_posts_introduction.html`
  - `.../posts/docs/inventory-api/reference/GraphQL/v1.0.0`
    → `developer_wayfair_io_posts_docs_inventory-api_reference_GraphQL_v100.html`
- `<output_dir>/manifest_wayfair_dev_<locale_tag>_<flag>.json`

manifest 结构：

```json
{"excel_path": "...", "locale": "zh-CN", "flag": "20260807",
 "generated_at": "...", "total": 26, "ok": 26, "failed": 0,
 "items": [{"label": "1. Introduction", "url": "...", "kind": "post",
            "slug": "developer_wayfair_io_posts_introduction",
            "file": "data/wayfair/html/....html", "locale": "zh-CN",
            "title": "简介", "html_len": 12345, "cjk_char_count": 688,
            "status": "ok", "error": null}]}
```

`cjk_char_count` 统计 `[一-鿿]`，是判断「这一页确实拿到中文」的核对指标；
`zh-CN` 下若为 0 说明该页没有官方中文版，必须暴露出来而不是当成成功。

## 逻辑说明
1. `extract_urls_from_excel` 取 URL；按 URL 去重（保留首个 label）
2. 线程池并发处理，每条：
   - `parse_post_url` 判类型
   - `post` → `fetch_post` → `richtext_to_html` → `build_html_document`
   - `reference` → `fetch_reference_html`；`<body` 不在返回值中则 `build_html_document` 包装，
     标题取 `<title>` 或回退到 `api_id`
   - `get_filename_from_url` 生成 slug，写文件
3. 单条失败只记 `status="failed"` + `error`，不中断整体
4. 写 manifest，日志打印 `ok/failed` 汇总；有失败则日志 `error` 级别列出

## 依赖的外部接口
见 `graphql_post` / `fetch_post` / `fetch_reference_html` 的 schema。

## SQL
无。
