# kdb.mining.common.multimodal.process.MultimodalProcess.prepare_image_hash_blacklist

## Signature

`prepare_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> None`

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

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
