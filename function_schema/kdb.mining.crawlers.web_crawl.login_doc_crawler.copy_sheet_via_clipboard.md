# kdb.mining.crawlers.web_crawl.login_doc_crawler.copy_sheet_via_clipboard

## Signature

`copy_sheet_via_clipboard(page, context, settle_ms=9000, retries=3)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

飞书表格（`/sheets/`、`doc_type: lark_sheet`）的正文画在 **canvas** 上，
DOM 里 `<table>` 是 0 个，`lark` 那套块提取只能拿到几十字的界面文案。

配置接口，表格内容是 **WebSocket** 同步的。所以没有"截页面自己的请求"这条路
（`capture_pdf_bytes` / `fetch_wecom_doc_via_browser` 那套在这里不适用）。

可行的只剩借飞书自己的复制能力：点进网格 → 全选 → 复制 → 读剪贴板，拿到 TSV。

## copy_sheet_via_clipboard

### Inputs
- `page` — playwright Page，已 goto 到表格 URL
- `context` — BrowserContext，用来 `grant_permissions(['clipboard-read','clipboard-write'])`
- `settle_ms` (int, 默认 9000) — 首次等待渲染的时间
- `retries` (int, 默认 3)

### Outputs
- 成功：TSV 字符串（行以 `\n`、列以 `\t` 分隔）
- 复制没生效：`None`
- 文档禁止复制：抛 `CopyForbidden`

### 必须先清空剪贴板（血的教训）
第一版没清剪贴板，**4 张不同的表返回了同一份内容**（320375 字，md5 一致），
四条日志全是 `status=ok`。复制失败时 `readText()` 读到的是上一张表的残留，
于是「内容看着有，实际张冠李戴」，灌进库里没人能发现。

现在的做法：复制前写一个 `__CLIPBOARD_EMPTY_<ts>__` 哨兵进剪贴板，
读回来还是哨兵就判失败。**任何走剪贴板的抓取都必须这么做。**

## _detect_copy_forbidden

按下 Cmd+C 后飞书会弹 toast：
`由于文档权限设置，如需复制请联系 @XXX 开通可编辑权限。`

### Inputs
- `page`

### Outputs
- 命中：提示文案首行（≤120 字）
- 未命中 / 读取失败：`None`

判定条件是 toast 里同时含「权限」和（「复制」/「导出」/「下载」）。
用途是把**权限问题**和**技术故障**分开：前者重试多少次都没用，直接抛 `CopyForbidden`。

## tsv_to_blocks

### Inputs
- `tsv` (str)

### Outputs
- `[{key:'sheet', top:0, type:'table', text:<原始TSV>, md:<markdown表格>, images:[]}]`
- 空输入返回 `[]`

整张表压成**一个块**，保住行列对应关系（拆块会让表头和数据行失联）。
短行补齐到最宽列宽，单元格里的 `|` 转义成 `\|`。

## 已知边界

文档所有者关掉复制权限时，代码层面无解，只能去要权限。
截图 + OCR 能绕过，但那是规避所有者明确设置的管控，需业务方先拍板，**不要默认这么做**。

3 张被 DLP 挡住，详见 `docs/payoneer_olive_sublink_crawl.md`。

## SQL

无。

## Source

`src/kdb/mining/crawlers/web_crawl/login_doc_crawler.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
