# kdb.services.forge_compat.api.legacy_routes.list_file_names

## Signature

`list_file_names(request: ListFileNamesRequest) -> ListFileNamesResponse`

## Inputs

`index_name`、可选 `keyword`、`size`。

## Outputs

`ListFileNamesResponse`，返回来源文件及 qa/segment 分布。

## SQL

无 SQL；调用 ES8 aggregation。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
