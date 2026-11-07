# kdb.mining.generation.processing.wordtotext.parse_pdf_to_json

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

`src/kdb/mining/generation/processing/wordtotext.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
