# wordtotext._normalize_pdf_image_ext

## Purpose

Normalize image extensions returned by PyMuPDF before writing extracted PDF images to disk.

## Inputs

- `image_ext`: optional string from a PyMuPDF image block or extracted resource.

## Outputs

- `str`: lowercase extension without a leading dot. Defaults to `png` when empty or non-string.

## SQL

No SQL access.
