# legacy_routes.delete_by_file

## Inputs

与预览相同但无 sample_size。

## Outputs

`DeleteByFileResponse`，包括 deleted_count、snapshot_path；参数错误 HTTP 400。

## SQL

无 SQL；删前 JSONL 快照，调用 ES8 update_by_query。
