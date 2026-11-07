# LegacySearchDataInterfaceMixin.delete_by_file

## Inputs
旧删除参数和 snapshot_dir。

## Outputs
旧 `{success, deleted_count, snapshot_path, message}` 结构。

## SQL
无；写 JSONL 快照并执行 ES8 update_by_query 软删除。
