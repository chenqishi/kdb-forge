# kdb.services.forge_compat.api.retrieval_app.app

## Inputs

进程环境 `KDB_FORGE_CONFIG`、`KDB_SEARCH_BASIC_USER`、`KDB_SEARCH_BASIC_PASSWORD`；仅挂载
`search_routes` 的检索路由。ES 凭据来自 0600 运行配置，不进入 HTTP 参数。

## Outputs

只提供 `/health`、`/search`、`/web_search`。不挂载 `/knowledge/insert`、`/knowledge/delete` 或
`/knowledge/modify_direct_update`，公网检索进程因此不会暴露写入接口。

## SQL

无。

## Source

`src/kdb/services/forge_compat/api/retrieval_app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
