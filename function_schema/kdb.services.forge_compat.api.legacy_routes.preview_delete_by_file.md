# kdb.services.forge_compat.api.legacy_routes.preview_delete_by_file

## Signature

`preview_delete_by_file(request: PreviewDeleteByFileRequest) -> PreviewDeleteByFileResponse`

## Inputs

`index_name`、非空 `file_names`、`match_mode` exact/fuzzy、可选 data_types/audit_results/sample_size。

## Outputs

`PreviewDeleteByFileResponse`；只读，参数错误 HTTP 400。

## SQL

无 SQL；调用 ES8 count/aggregation/sample。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
