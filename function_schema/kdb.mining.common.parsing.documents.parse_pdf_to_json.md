# kdb.mining.common.parsing.documents.parse_pdf_to_json

## Signature

`parse_pdf_to_json(pdf_path, data_dir)`

## Purpose

Parse a PDF into per-page JSON content containing text blocks and extracted images for downstream multimodal processing.

## Inputs

- `pdf_path`: local PDF file path.
- `data_dir`: directory where extracted images should be saved.

## Outputs

- JSON string keyed by 1-based page numbers. Each page value is a list of items:
  - Text item: `{"type": "text", "text_content": str, "image_path": None}`
  - Image item: `{"type": "image", "text_content": None, "image_path": str, ...optional metadata}`
- On fatal parse failure, returns `{"error": str}` as JSON.

## SQL

No SQL access.

## Source

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
