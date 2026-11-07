# multimodal_process.process_multimodal_data_one_file

## Purpose

Process one parsed document JSON file/page payload through `MultimodalProcess`, writing the multimodal-enriched output and URL metadata map.

## Inputs

- `document_multidata_process`: config path or `MultimodalProcess` instance.
- `client_name`: upload namespace.
- `process_data_path`: JSON file path or already-loaded dict payload.
- `multimodal_data_info_dict`: mutable dict receiving public URL keyed processed items.
- `output_path`: optional path for processed JSON output.

## Outputs

- `dict`: processed payload keyed by page.

## SQL

No SQL access.
