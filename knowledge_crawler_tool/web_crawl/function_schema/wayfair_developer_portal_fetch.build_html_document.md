# build_html_document

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
把 HTML 片段包装成带溯源信息的完整 HTML 文档。

两处用到：
1. Post 类：`richtext_to_html` 的输出必须包一层才是完整页面
2. Reference 类：`fetch_reference_html` 返回值**不含 `<body>`** 时补包装

`<body>` 是硬要求 —— 下游 `WebBatchCrawler.extract_formatted_text_by_flat` 找不到 `<body>`
会直接返回 `""`，整页内容会在 `knowledge_html_clear_by_dify.py:146` 被静默 `continue` 掉。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| title | str | 是 | - | 写入 `<title>` 与首个 `<h1>` |
| source_url | str | 是 | - | 原始门户 URL，写入溯源注释与 `<link rel="canonical">` |
| locale | str | 是 | - | `zh-CN` / `en-US`，写入 `<html lang>` |
| inner_html | str | 是 | - | 正文片段 |
| fetched_at | str | 否 | `None` | ISO 时间串；`None` 时取当前本地时间 |

## Outputs
| 类型 | 说明 |
|------|------|
| str | 完整 HTML 文档 |

结构：

```html
<!DOCTYPE html>
<html lang="{locale}">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<link rel="canonical" href="{source_url}" />
<!-- source_url: ...
     locale: ...
     fetched_at: ... -->
</head>
<body>
<h1>{title}</h1>
{inner_html}
</body>
</html>
```

`title` 与 `source_url` 经 `html.escape` 后写入。

## 依赖的外部接口
无。

## SQL
无。
