# ecommerce_query_mining.extract_mercado_site_platforms

## 描述
从 query 文本中提取美客多站点级平台。只要文本同时出现美客多/Mercado Libre 及国家站点信息，就返回 `美客多{国家}站点`，例如 `美客多墨西哥站点`、`美客多巴西站点`。美客多不同站点政策差异较大，因此站点级平台不能被合并成普通 `美客多平台`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 原始 query |

## Outputs

| 类型 | 说明 |
|------|------|
| list[str] | 站点级平台列表 |

## SQL

无 SQL。
