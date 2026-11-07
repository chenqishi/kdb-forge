# LegacySearchDataInterfaceMixin file operations

## Inputs/Outputs
保留 `list_file_names`、`resolve_file_name`、`preview_delete_by_file`、`delete_by_file`、
`dice_similarity`、`get_data_by_id`、`update_data`、`delete_data`、`update_data_value`、
`get_unique_values` 的旧参数和返回结构；删除仍为软删除并先写快照。

## SQL
无；读写 Elasticsearch，快照写 JSONL 文件。
