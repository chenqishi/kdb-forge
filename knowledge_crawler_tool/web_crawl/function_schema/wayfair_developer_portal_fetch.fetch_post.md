# fetch_post

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
按 slug + locale 取一篇 Post 的**标题 + Contentful Rich Text 正文 JSON + 内嵌资源清单**。

## 依赖的外部接口

经 `graphql_post` 调内容 BFF。query 与门户前端 chunk `759-*.js` 模块 `50839` 中的 `Post` **逐字一致**
（字段集合不可随意增删：加 `title`/`entries` 等未在 schema 中的字段会整条请求报错）：

```graphql
query Post($slug: String!, $locale: String) {
  postCollection(where: {slug: $slug}, locale: $locale, limit: 1) {
    items {
      title
      body {
        json
        links { assets { block { sys { id } contentType url } } }
      }
      sys { id }
    }
  }
}
```

`locale` 取值只有两个（前端语言开关仅这两项）：`en-US`、`zh-CN`。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| slug | str | 是 | - | 如 `introduction`、`FAQs`、`Cg-Orders-Guide`（**大小写敏感**） |
| locale | str | 否 | `'zh-CN'` | `zh-CN` / `en-US` |

## Outputs
| 类型 | 说明 |
|------|------|
| dict | `{"title": str, "body_json": dict, "assets": list[dict], "sys_id": str}` |

- `body_json`：Contentful Rich Text 文档根节点（`nodeType == "document"`）
- `assets`：`links.assets.block` 列表，每项 `{"sys": {"id": ...}, "contentType": ..., "url": ...}`

## 异常
- `postCollection.items` 为空 → `LookupError`（该 slug 在该 locale 下无内容）

## SQL
无。
