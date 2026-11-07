# multimodal_process._get_image_content_hash

## Purpose

Compute a stable content hash for a local image file.

## Inputs

- `image_path`: local file path.

## Outputs

- `str | None`: SHA-256 hex digest, or `None` when the path is invalid or the file cannot be read.

## SQL

No SQL access.
