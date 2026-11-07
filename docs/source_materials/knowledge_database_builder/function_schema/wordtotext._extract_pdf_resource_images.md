# wordtotext._extract_pdf_resource_images

## Purpose

Legacy fallback extraction for PDF image resources using `page.get_images()` and `pdf.extract_image(xref)`.

## Inputs

- `pdf`: PyMuPDF document object.
- `page`: PyMuPDF page object.
- `page_num`: 1-based PDF page number.
- `data_dir`: directory where extracted image files should be saved.

## Outputs

- `list[dict]`: image items compatible with `parse_pdf_to_json`.

## SQL

No SQL access.
