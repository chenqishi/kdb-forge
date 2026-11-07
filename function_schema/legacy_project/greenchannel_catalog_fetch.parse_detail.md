# greenchannel_catalog_fetch.parse_detail / parse_catalog / render

抓取绿通官网（greenchannel.payoneer.com.cn）平台页并解析结构化板块。

## Inputs
- `render(url, out_path, budget_ms=20000, timeout=120)`：无头 Chrome 渲染，落盘 DOM
- `parse_catalog(html_path)` → `{platform_id: 平台名}`
- `parse_detail(html_path)` → `(platform, {板块名: {'html_content','text_content'}})`

## Outputs
- `<out-dir>/PlatformId_<id>.html`：渲染后 DOM（供既有解析器复用）
- `<out-dir>/manifest.json`：`{pid: {platform_id, catalog_name, platform, sections, html_file}}`

## 关键事实（实测 2026-09-01）
- 页面是 **OutSystems SPA**：裸 requests / firecrawl 只拿到 2328 字节空壳
  （"JavaScript is required"），**必须渲染**。
  用本机 playwright 缓存里的 Chrome：`/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`
  `--headless --dump-dom --virtual-time-budget=20000`，不新装依赖。
- 板块 id 映射：`Intro_1` 入驻介绍 / `Intro_2` 平台特点 / `Intro_3` 热卖品类 /
  `Intro_4` 平台数据 / `Intro_5` 回款周期。
  （`special_clear_method.py` 里 `sections` 的 id 是空串，历史遗留，本脚本按上表补齐）
- 平台名取 `span.heading5`；正文取板块内 `div.html-font`。
- 目录页共 **48 个平台**。

## 下游
解析与清洗**复用既有方法**，不走通用挖掘：
`knowledge_clear_tool/special_clear_method.py`
→ `clear_greenchannel_payoneer_data(html_file)`
产出 qa 记录：`title=f'{platform}{板块名}'`、`data_type=qa`、`from_type=html`、
`platform=payoneer`、`quality_level=high`、`indexes=[{'text':...}]`、
`ext_info={ecommerce_platform, from_file_name}`。

## SQL / ES
写入 ES 索引 `payoneer_olive`；类目按平台名映射到 `primary_category`
（`category_infos[].source='platform_backfill'`）。
参考被删的历史条目 `_id=93b1602253f9bd9a1bef5114ed49db79`（美客多入驻介绍，2025-04-07 入库）。
