# kdb.services.forge_compat.api.legacy_routes.delete_by_file

## Signature

`delete_by_file(request: DeleteByFileRequest) -> DeleteByFileResponse`

## Inputs

与预览相同但无 sample_size。

## Outputs

`DeleteByFileResponse`，包括 deleted_count、snapshot_path；参数错误 HTTP 400。

## SQL

无 SQL；删前 JSONL 快照，调用 ES8 update_by_query。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
