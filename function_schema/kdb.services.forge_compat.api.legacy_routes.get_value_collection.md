# kdb.services.forge_compat.api.legacy_routes.get_value_collection

## Signature

`get_value_collection(request: ValueCollectionRequest) -> ValueCollectionResponse`

## Inputs

`index_name`、`field_name`、`size`、`include_doc_count`、可选 `extra_query`。路径兼容 `/get_value_collection` 与 `/get_unique_values`。

## Outputs

`ValueCollectionResponse`，返回唯一值及数量。

## SQL

无 SQL；调用 ES8 terms aggregation。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
