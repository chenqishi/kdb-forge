# legacy_routes.get_value_collection

## Inputs

`index_name`、`field_name`、`size`、`include_doc_count`、可选 `extra_query`。路径兼容 `/get_value_collection` 与 `/get_unique_values`。

## Outputs

`ValueCollectionResponse`，返回唯一值及数量。

## SQL

无 SQL；调用 ES8 terms aggregation。
