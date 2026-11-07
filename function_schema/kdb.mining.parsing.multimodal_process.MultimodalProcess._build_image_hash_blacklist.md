# kdb.mining.parsing.multimodal_process.MultimodalProcess._build_image_hash_blacklist

## Signature

`MultimodalProcess._build_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, str], set]`

## Purpose

Scan parsed document payload image paths, count repeated image content hashes, and identify hashes that should be skipped during OCR/image understanding.

## Inputs

- `data_payload`: parsed document JSON payload keyed by page.

## Outputs

- `tuple[dict, dict, set]`:
  - hash count map: `{sha256: occurrence_count}`
  - image path to hash map: `{image_path: sha256}`
  - blacklist set containing hashes whose counts are greater than `image_hash_blacklist_threshold`

## SQL

No SQL access.

## Source

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
