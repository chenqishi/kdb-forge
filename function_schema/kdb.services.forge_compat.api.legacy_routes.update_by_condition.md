# kdb.services.forge_compat.api.legacy_routes.update_by_condition

## Signature

`update_by_condition(request: UpdateByConditionRequest) -> UpdateByConditionResponse`

## Inputs

`index_name`、非空 `update_fields`、非空 `conditions`。

## Outputs

`UpdateByConditionResponse`；保留旧 updated_count=0 口径。

## SQL

无 SQL；调用 ES8 update_by_query。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
