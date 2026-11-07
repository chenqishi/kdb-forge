# kdb.mining.parsing.multimodal_process.process_multimodal_data_one_file

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

`src/kdb/mining/parsing/multimodal_process.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
