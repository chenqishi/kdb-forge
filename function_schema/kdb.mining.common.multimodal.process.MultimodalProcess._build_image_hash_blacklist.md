# kdb.mining.common.multimodal.process.MultimodalProcess._build_image_hash_blacklist

## Signature

`_build_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, str], set]`

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

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
