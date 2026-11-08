# kdb.mining.common.parsing.documents._extract_pdf_resource_images

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

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
