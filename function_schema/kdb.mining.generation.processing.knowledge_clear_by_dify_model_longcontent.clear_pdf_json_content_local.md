# kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent.clear_pdf_json_content_local

## Signature

`clear_pdf_json_content_local(pdf_json_file, output_file, business_context, from_file_name, use_image_content=0, model_name=None, provider=None, quality_profile='', max_chars=12000, image_placeholder_map=None)`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

## Source

`src/kdb/mining/generation/processing/knowledge_clear_by_dify_model_longcontent.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
