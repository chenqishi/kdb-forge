# parse_post_url

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
把 `https://developer.wayfair.io/posts/...` URL 解析成内容 API 需要的取数参数。

门户只有两类页面，路由由前端 `pages/posts/[...slug]` 决定：

| URL 形态 | 类型 | 取数方式 |
|---|---|---|
| `/posts/<slug>` | `post` | Contentful `Post` query（rich text JSON） |
| `/posts/docs/<apiId>/reference/<protocol>/<version>` | `reference` | `ReferenceHtml` query（返回现成 HTML） |

判定依据与前端一致：slug 数组首段是否等于 `docs`。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| url | str | 是 | - | 门户页面 URL |

## Outputs
| 类型 | 说明 |
|------|------|
| dict | 见下 |

`post` 类：
```python
{"kind": "post", "slug": "introduction", "url": <原 url>}
```

`reference` 类：
```python
{"kind": "reference", "api_id": "inventory-api", "api_protocol": "GraphQL",
 "version": "v1.0.0", "url": <原 url>}
```

## 异常
- URL 路径中不含 `/posts/` → `ValueError`
- `docs` 形态但路径段数不足 5 → `ValueError`

## 逻辑说明
1. `urlparse(url).path` 按 `/` 切分，定位 `posts` 段，取其后的全部段为 `slug_parts`
2. `slug_parts[0] == "docs"` → reference，取 `slug_parts[1]`=api_id、`slug_parts[3]`=api_protocol、
   `slug_parts[4]`=version（与前端 `[e[1], e[3], e[4]]` 逐位对齐）
3. 否则 → post，`slug = slug_parts[0]`

## 依赖的外部接口
无。

## SQL
无。
