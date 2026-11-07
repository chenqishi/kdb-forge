# graphql_post

## 所属文件
`knowledge_crawler_tool/web_crawl/wayfair_developer_portal_fetch.py`

## 功能
向 Wayfair 开发者门户的**内容 BFF** 发一次 GraphQL 请求，带重试。

## 依赖的外部接口（重要，勿改端点）

`POST https://api.wayfair.io/content/v1/developer-portal-bff/graphql`

接口来源：门户前端 bundle `_next/static/chunks/pages/_app-*.js` 里的 Apollo link 定义

```js
cZ="/graphql", cY="https://api.wayfair.io",
c1="".concat(cY,"/content/v1/developer-portal-bff")
lt = new HttpLink({uri: (PROD ? c1 : cJ) + cZ, credentials:"same-origin"})
```

同域另外两个 BFF **不可用**，实测：

| 端点 | 结果 |
|---|---|
| `https://api.wayfair.io/content/v1/developer-portal-bff/graphql` | 200，**无需鉴权** |
| `https://api.wayfair.io/public/v1/developer-portal-bff/graphql` | 403 `graphql operation not permitted` |
| `https://api.wayfair.io/v1/developer-portal-bff/graphql` | 401 `Unauthorized` |

请求头：`content-type: application/json`、`origin: https://developer.wayfair.io`、桌面 UA。
不需要 cookie / token。

## Inputs
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| query | str | 是 | - | GraphQL query 文本 |
| variables | dict | 是 | - | query 变量 |
| retries | int | 否 | `3` | 总尝试次数 |
| timeout | int | 否 | `90` | 单次超时秒数；reference 类响应可达 500KB，勿调太小 |
| backoff | float | 否 | `2.0` | 失败后 sleep 秒数（线性） |

## Outputs
| 类型 | 说明 |
|------|------|
| dict | 解析后的响应体，形如 `{"data": {...}}` |

## 异常
- 重试耗尽仍失败（网络异常 / 非 200）→ `RuntimeError`，消息带最后一次错误
- 响应体含 `errors` 字段 → `RuntimeError`，消息带 `errors`

实测该端点在并发时偶发 `504 Gateway Timeout`，重试一次即恢复，所以重试是必须的而非可选。

## SQL
无。
