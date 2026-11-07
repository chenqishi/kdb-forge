# kdb.mining.crawlers.web_crawl.greenchannel_catalog_fetch.parse_detail

## Signature

`parse_detail(html_path)`

## Description

抓取绿通官网（greenchannel.payoneer.com.cn）平台页并解析结构化板块。

## Inputs

- `render(url, out_path, budget_ms=20000, timeout=120)`：无头 Chrome 渲染，落盘 DOM
- `parse_catalog(html_path)` → `{platform_id: 平台名}`
- `parse_detail(html_path)` → `(platform, {板块名: {'html_content','text_content'}})`

## Outputs

- `<out-dir>/PlatformId_<id>.html`：渲染后 DOM（供既有解析器复用）
- `<out-dir>/manifest.json`：`{pid: {platform_id, catalog_name, platform, sections, html_file}}`

## 下游

解析与清洗**复用既有方法**，不走通用挖掘：
`src/kdb/mining/generation/processing/special_clear_method.py`
→ `clear_greenchannel_payoneer_data(html_file)`
产出 qa 记录：`title=f'{platform}{板块名}'`、`data_type=qa`、`from_type=html`、
`platform=payoneer`、`quality_level=high`、`indexes=[{'text':...}]`、
`ext_info={ecommerce_platform, from_file_name}`。

## SQL / ES

写入 ES 索引 `payoneer_olive`；类目按平台名映射到 `primary_category`
（`category_infos[].source='platform_backfill'`）。
参考被删的历史条目 `_id=93b1602253f9bd9a1bef5114ed49db79`（美客多入驻介绍，2025-04-07 入库）。

## Source

`src/kdb/mining/crawlers/web_crawl/greenchannel_catalog_fetch.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
