# kdb.retrieval.maintenance.retire_superseded.rollback

## Signature

`rollback(config_path: str, index: str, rollback_file: str, bulk_batch: int=DEFAULT_BULK_BATCH, execute: bool=False) -> Dict[str, Any]`

## Description

按 `rollback.jsonl` 把 `del_flag` / `flag` 写回原值，撤销一次 `retire`。默认 dry-kdb.entrypoints.cli.generate_segments。

## Inputs

- `config_path` (str)、`index` (str)、`rollback_file` (str)
- `bulk_batch` (int, 默认 200)、`execute` (bool, 默认 False)

## Outputs

`Dict` — dry-kdb.entrypoints.cli.generate_segments 时 `{planned, dry_run}`；写回时 `bulk_update_doc` 的 `{updated, failed}`。

## SQL / ES schema

写 `del_flag`（缺失按 0）与 `flag`（原值为 None 时不写，保持不存在）。

## SQL

无 MySQL。

## Source

`src/kdb/retrieval/maintenance/retire_superseded.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
