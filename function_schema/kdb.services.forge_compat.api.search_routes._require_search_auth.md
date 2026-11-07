# kdb.services.forge_compat.api.search_routes._require_search_auth

## Signature

`_require_search_auth(request: Request, credentials: Optional[HTTPBasicCredentials]=Security(_basic)) -> Optional[HTTPBasicCredentials]`

## Inputs

HTTP Basic credentials；期望值从 `KDB_SEARCH_BASIC_USER` 与 `KDB_SEARCH_BASIC_PASSWORD` 读取。

## Outputs

认证成功返回凭据对象；缺少服务凭据或校验失败返回 HTTP 401/503。健康检查不依赖此函数。

## SQL

无。

## Source

`src/kdb/services/forge_compat/api/search_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
