# multimodal_process._build_image_hash_blacklist

## Purpose

Scan parsed document payload image paths, count repeated image content hashes, and identify hashes that should be skipped during OCR/image understanding.

## Inputs

- `data_payload`: parsed document JSON payload keyed by page.

## Outputs

- `tuple[dict, dict, set]`:
  - hash count map: `{sha256: occurrence_count}`
  - image path to hash map: `{image_path: sha256}`
  - blacklist set containing hashes whose counts are greater than `image_hash_blacklist_threshold`

## SQL

No SQL access.
