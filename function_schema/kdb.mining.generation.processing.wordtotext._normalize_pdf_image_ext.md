# kdb.mining.generation.processing.wordtotext._normalize_pdf_image_ext

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

`src/kdb/mining/generation/processing/wordtotext.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
