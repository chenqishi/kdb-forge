# fetch_reference_html

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
取 API Reference 页（`/posts/docs/<apiId>/reference/<protocol>/<version>`）的 HTML。
这类页面服务端直接返回渲染好的 HTML（SpectaQL 产物），不需要本地渲染。

## 依赖的外部接口

经 `graphql_post` 调内容 BFF。query 与门户前端 chunk `pages/posts/[...slug]-*.js` 逐字一致：

```graphql
query ReferenceHtml($where: ReferenceFilter!) { referenceHtml(where: $where) }
```

变量：

```json
{"where": {"bucketName": "wf-developer-portal-prod",
           "apiProtocol": "GraphQL", "apiId": "...", "version": "v1.0.0"}}
```

### 中文版规则（关键）

前端源码：

```js
apiId: "en-US" === (a = a || "en-US") ? e : e + "-" + a
```

即 **非 `en-US` 时把 locale 拼到 apiId 后面**，中文版 apiId = `<apiId>-zh-CN`
（例：`inventory-api` → `inventory-api-zh-CN`）。
URL 本身没有中文变体，中文只体现在这个 apiId 后缀上。

`bucketName` 由环境决定，PROD 固定 `wf-developer-portal-prod`（DEV 为 `wf-developer-portal-dev`）。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| api_id | str | 是 | - | 不带 locale 后缀的原始 apiId |
| api_protocol | str | 否 | `'GraphQL'` | 来自 URL 第 4 段 |
| version | str | 否 | `'v1.0.0'` | 来自 URL 第 5 段 |
| locale | str | 否 | `'zh-CN'` | `en-US` 时不拼后缀 |
| bucket_name | str | 否 | `'wf-developer-portal-prod'` | 环境 bucket |

## Outputs
| 类型 | 说明 |
|------|------|
| str | `referenceHtml` 字符串 |

**注意返回值不保证是完整 HTML 文档**：实测部分 API（如 `orders-api-zh-CN`、
`inventory-visibility-onhand-api-zh-CN`）返回的是以 `<style>` 开头的**片段**，没有
`<html>` / `<body>`。调用方必须判断并补包装，否则下游
`WebBatchCrawler.extract_formatted_text_by_flat` 找不到 `<body>` 会直接返回 `""`。

## 异常
- `referenceHtml` 为空 / `None` → `LookupError`

## SQL
无。
