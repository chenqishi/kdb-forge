# legacy_routes.update_by_condition

## Inputs

`index_name`、非空 `update_fields`、非空 `conditions`。

## Outputs

`UpdateByConditionResponse`；保留旧 updated_count=0 口径。

## SQL

无 SQL；调用 ES8 update_by_query。
