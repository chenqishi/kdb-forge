# wordtotext._extract_rendered_pdf_images

## Purpose

Extract only images that are actually rendered on a PDF page using PyMuPDF text-dict image blocks.

## Inputs

- `page`: PyMuPDF page object.
- `page_num`: 1-based PDF page number.
- `data_dir`: directory where extracted image files should be saved.

## Outputs

- `list[dict]`: image items compatible with `parse_pdf_to_json`. Empty list is a valid result when the page renders no images.

## SQL

No SQL access.
