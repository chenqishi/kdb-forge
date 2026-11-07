# multimodal_process.__init__

## Purpose

Initialize multimodal processing configuration, upload clients, Dify clients, and duplicate image hash blacklist state.

## Inputs

- `config_path`: either a JSON config file path or an already-loaded config dict.
- Relevant hash blacklist config keys:
  - `enable_image_hash_blacklist`: bool-like, default `true`.
  - `image_hash_blacklist_threshold`: int-like, default `10`; hashes with counts greater than this value are blacklisted.

## Outputs

- Initializes instance fields for upload, OCR, image understanding, and hash blacklist caches.

## SQL

No SQL access.
