# kdb.mining.parsing.multimodal_process.MultimodalProcess.prepare_image_hash_blacklist

## Signature

`MultimodalProcess.prepare_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> None`

## Purpose

Prepare per-document duplicate image hash blacklist state before batch multimodal processing.

## Inputs

- `data_payload`: parsed document JSON payload keyed by page.

## Outputs

- Updates instance fields:
  - `image_hash_counts`
  - `image_hash_by_path`
  - `image_hash_blacklist`

## SQL

No SQL access.

## Source

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
