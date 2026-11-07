# kdb.mining.parsing.multimodal_process.MultimodalProcess.process_one_data

## Signature

`MultimodalProcess.process_one_data(self, json_data: Dict[str, Any], client_name: str='default', context: str='', size_threshold: int=None, area_threshold: int=None, ocr_valid_num_threshold: int=20) -> Dict[str, Any]`

## Purpose

Process one multimodal item, including image validation, optional upload, OCR, OCR-based filtering, and image understanding.

## Inputs

- `json_data`: item dict. Image items use `type=image`, `image_path`, and optional `public_url`, `s3_path`, `url`, `image_content_hash`.
- `client_name`: upload namespace.
- `context`: image understanding context with optional `{placeholder}`.
- `size_threshold`: optional byte threshold.
- `area_threshold`: optional pixel area threshold.
- `ocr_valid_num_threshold`: OCR richness threshold.

## Outputs

- Result dict with public URL, S3 path, OCR/understanding outputs, validity fields, filename, extern URL, and hash blacklist metadata.

## SQL

No SQL access.

## Source

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
