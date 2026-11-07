# multimodal_process.prepare_image_hash_blacklist

## Purpose

Prepare per-document duplicate image hash blacklist state before batch multimodal processing.

## Inputs

- `data_payload`: parsed document JSON payload keyed by page.

## Outputs

- Updates instance fields:
  - `image_hash_counts`
  - `image_hash_by_path`
  - `image_hash_blacklist`

## SQL

No SQL access.
