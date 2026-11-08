# kdb.mining.common.parsing.documents._write_pdf_image_file

## Signature

`_write_pdf_image_file(image_data, image_ext, page_num, img_index, data_dir, metadata=None)`

## Purpose

Write extracted PDF image bytes to the page image directory and return the standard multimodal image item.

## Inputs

- `image_data`: bytes-like object containing the encoded image.
- `image_ext`: image extension from PyMuPDF.
- `page_num`: 1-based PDF page number.
- `img_index`: 0-based image index for that page.
- `data_dir`: destination directory for extracted image files.
- `metadata`: optional dict copied into the returned item.

## Outputs

- `dict`: `{type, text_content, image_path, ...metadata}` compatible with downstream multimodal processing.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
