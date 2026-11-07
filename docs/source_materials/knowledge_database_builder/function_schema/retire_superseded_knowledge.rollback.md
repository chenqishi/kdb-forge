# rollback

## 所属文件
`data_control_tools/retire_superseded_knowledge.py`

## 功能描述
按 `rollback.jsonl` 把 `del_flag` / `flag` 写回原值，撤销一次 `retire`。默认 dry-run。

## Inputs
- `config_path` (str)、`index` (str)、`rollback_file` (str)
- `bulk_batch` (int, 默认 200)、`execute` (bool, 默认 False)

## Outputs
`Dict` — dry-run 时 `{planned, dry_run}`；写回时 `bulk_update_doc` 的 `{updated, failed}`。

## SQL / ES schema
写 `del_flag`（缺失按 0）与 `flag`（原值为 None 时不写，保持不存在）。

## SQL
无 MySQL。
