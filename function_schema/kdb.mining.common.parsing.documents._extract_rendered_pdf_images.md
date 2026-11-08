# kdb.mining.common.parsing.documents._extract_rendered_pdf_images

## Signature

`_extract_rendered_pdf_images(page, page_num, data_dir)`

## Purpose

Extract only images that are actually rendered on a PDF page using PyMuPDF text-dict image blocks.

## Inputs

- `page`: PyMuPDF page object.
- `page_num`: 1-based PDF page number.
- `data_dir`: directory where extracted image files should be saved.

## Outputs

- `list[dict]`: image items compatible with `parse_pdf_to_json`. Empty list is a valid result when the page renders no images.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
