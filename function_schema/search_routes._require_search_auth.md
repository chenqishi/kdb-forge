# search_routes._require_search_auth

## Inputs

HTTP Basic credentials；期望值从 `KDB_SEARCH_BASIC_USER` 与 `KDB_SEARCH_BASIC_PASSWORD` 读取。

## Outputs

认证成功返回凭据对象；缺少服务凭据或校验失败返回 HTTP 401/503。健康检查不依赖此函数。

## SQL

无。
