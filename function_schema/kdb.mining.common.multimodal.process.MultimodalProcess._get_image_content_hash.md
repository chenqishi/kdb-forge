# kdb.mining.common.multimodal.process.MultimodalProcess._get_image_content_hash

## Signature

`_get_image_content_hash(image_path: str) -> Optional[str]`

## Purpose

Compute a stable content hash for a local image file.

## Inputs

- `image_path`: local file path.

## Outputs

- `str | None`: SHA-256 hex digest, or `None` when the path is invalid or the file cannot be read.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
