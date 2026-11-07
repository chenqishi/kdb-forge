# richtext_to_html

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
把 Contentful Rich Text 文档 JSON 渲染成 HTML 片段。

Post 类页面的正文只有 rich text JSON，没有现成 HTML，必须本地渲染才能落成 `.html` 供下游
（`extract_formatted_text_by_flat` → `knowledge_html_clear_by_dify` → QA）复用。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| body_json | dict | 是 | - | rich text 根节点（`nodeType == "document"`） |
| assets | list[dict] | 否 | `None` | `links.assets.block`，用于解析 `embedded-asset-block` |

## Outputs
| 类型 | 说明 |
|------|------|
| str | HTML 片段（不含 `<html>`/`<body>`），块级元素之间以换行分隔 |

## 支持的节点集合

已对全部 16 篇 zh-CN Post 做过全量 nodeType 统计，是一个**封闭集合**，无需通用渲染器：

| nodeType | 输出 |
|---|---|
| `document` | 直接渲染子节点 |
| `paragraph` | `<p>` |
| `heading-1` … `heading-6` | `<h1>` … `<h6>` |
| `unordered-list` | `<ul>` |
| `ordered-list` | `<ol>` |
| `list-item` | `<li>` |
| `table` | `<table>` |
| `table-row` | `<tr>` |
| `table-cell` | `<td>` |
| `table-header-cell` | `<th>`（当前数据未出现，预置） |
| `blockquote` | `<blockquote>`（当前数据未出现，预置） |
| `hr` | `<hr />` |
| `hyperlink` | `<a href="{data.uri}">` |
| `text` | 转义文本 + marks 包裹 |
| `embedded-asset-block` | 见下 |

marks（实测出现 4 种）：`bold`→`<strong>`、`italic`→`<em>`、`underline`→`<u>`、`code`→`<code>`。
多个 mark 时按固定顺序嵌套，保证输出稳定可测。

### embedded-asset-block

用 `node["data"]["target"]["sys"]["id"]` 去 `assets` 里按 `sys.id` 查 `{url, contentType}`：

- `contentType` 以 `image/` 开头 → `<img src="..." />`
- 以 `video/` 开头 → `<video controls><source src="..." type="..."></video>`
- 其它 → `<a href="...">`
- **id 查不到** → 输出 `<!-- missing asset: <id> -->` 并 `logging.warning`，不抛异常
  （单个资源缺失不该让整页抓取失败）

## 未知节点处理
不静默丢弃。渲染成 `<div data-unknown-node="<nodeType>">…子节点…</div>` 并 `logging.warning`。
Contentful 后续新增节点类型时，内容仍会保留在产物里而不是无声消失。

## 转义
所有 `text.value` 与属性值走 `html.escape`（属性用 `quote=True`）。

## 依赖的外部接口
无（纯函数，无网络）。

## SQL
无。
