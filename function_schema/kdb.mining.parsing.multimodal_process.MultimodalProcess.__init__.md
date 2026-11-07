# kdb.mining.parsing.multimodal_process.MultimodalProcess.__init__

## Signature

`MultimodalProcess.__init__(self, config_path: Union[str, Dict[str, Any]])`

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

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
