# multimodal_process.process_one_data

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
