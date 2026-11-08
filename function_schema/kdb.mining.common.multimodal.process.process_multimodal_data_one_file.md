# kdb.mining.common.multimodal.process.process_multimodal_data_one_file

## Signature

`process_multimodal_data_one_file(document_multidata_process: Union[str, MultimodalProcess], client_name: str, process_data_path: Union[str, Dict[str, Any]], multimodal_data_info_dict: Dict[str, Any], output_path: Union[str, None]) -> Dict[str, Any]`

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

## Source

`src/kdb/mining/common/multimodal/process.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
