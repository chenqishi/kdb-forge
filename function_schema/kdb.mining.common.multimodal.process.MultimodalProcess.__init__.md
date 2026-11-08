# kdb.mining.common.multimodal.process.MultimodalProcess.__init__

## Signature

`__init__(self, config_path: Union[str, Dict[str, Any]])`

## Purpose

Initialize multimodal processing configuration, upload clients, Dify clients, and duplicate image hash blacklist state.

## Inputs

- `config_path`: either a JSON config file path or an already-loaded config dict.
- Relevant hash blacklist config keys:
  - `enable_image_hash_blacklist`: bool-like, default `true`.
  - `image_hash_blacklist_threshold`: int-like, default `10`; hashes with counts greater than this value are blacklisted.

## Outputs

- Initializes instance fields for upload, OCR, image understanding, and hash blacklist caches.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
