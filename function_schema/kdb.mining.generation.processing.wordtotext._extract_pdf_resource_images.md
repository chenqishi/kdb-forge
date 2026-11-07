# kdb.mining.generation.processing.wordtotext._extract_pdf_resource_images

## Signature

`_extract_pdf_resource_images(pdf, page, page_num, data_dir)`

## Purpose

Legacy fallback extraction for PDF image resources using `page.get_images()` and `pdf.extract_image(xref)`.

## Inputs

- `pdf`: PyMuPDF document object.
- `page`: PyMuPDF page object.
- `page_num`: 1-based PDF page number.
- `data_dir`: directory where extracted image files should be saved.

## Outputs

- `list[dict]`: image items compatible with `parse_pdf_to_json`.

## SQL

No SQL access.

## Source

`src/kdb/mining/generation/processing/wordtotext.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
