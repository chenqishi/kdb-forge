# kdb.mining.common.parsing.documents._normalize_pdf_image_ext

## Signature

`_normalize_pdf_image_ext(image_ext)`

## Purpose

Normalize image extensions returned by PyMuPDF before writing extracted PDF images to disk.

## Inputs

- `image_ext`: optional string from a PyMuPDF image block or extracted resource.

## Outputs

- `str`: lowercase extension without a leading dot. Defaults to `png` when empty or non-string.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
