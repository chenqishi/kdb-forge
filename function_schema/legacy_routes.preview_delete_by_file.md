# legacy_routes.preview_delete_by_file

## Inputs

`index_name`、非空 `file_names`、`match_mode` exact/fuzzy、可选 data_types/audit_results/sample_size。

## Outputs

`PreviewDeleteByFileResponse`；只读，参数错误 HTTP 400。

## SQL

无 SQL；调用 ES8 count/aggregation/sample。
