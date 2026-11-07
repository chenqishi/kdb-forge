# kdb.mining.transformations.schema_trans.trans_web_excel_to_json_file

## Signature

`trans_web_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]]=None, image_save_dir: str=None, extra_field_name_dict: Dict[str, Any]=None)`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

## Source

`src/kdb/mining/transformations/schema_trans.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
