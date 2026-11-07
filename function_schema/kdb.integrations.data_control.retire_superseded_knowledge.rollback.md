# kdb.integrations.data_control.retire_superseded_knowledge.rollback

## Signature

`rollback(config_path: str, index: str, rollback_file: str, bulk_batch: int=DEFAULT_BULK_BATCH, execute: bool=False) -> Dict[str, Any]`

## Description

按 `rollback.jsonl` 把 `del_flag` / `flag` 写回原值，撤销一次 `retire`。默认 dry-kdb.mining.generation.run。

## Inputs

- `config_path` (str)、`index` (str)、`rollback_file` (str)
- `bulk_batch` (int, 默认 200)、`execute` (bool, 默认 False)

## Outputs

`Dict` — dry-kdb.mining.generation.run 时 `{planned, dry_run}`；写回时 `bulk_update_doc` 的 `{updated, failed}`。

## SQL / ES schema

写 `del_flag`（缺失按 0）与 `flag`（原值为 None 时不写，保持不存在）。

## SQL

无 MySQL。

## Source

`src/kdb/integrations/data_control/retire_superseded_knowledge.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
