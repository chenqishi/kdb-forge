# kdb.mining.parsing.multimodal_process.MultimodalProcess._get_image_content_hash

## Signature

`MultimodalProcess._get_image_content_hash(image_path: str) -> Optional[str]`

## Purpose

Compute a stable content hash for a local image file.

## Inputs

- `image_path`: local file path.

## Outputs

- `str | None`: SHA-256 hex digest, or `None` when the path is invalid or the file cannot be read.

## SQL

No SQL access.

## Source

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
