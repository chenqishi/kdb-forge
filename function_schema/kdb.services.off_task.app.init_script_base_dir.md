# kdb.services.off_task.app.init_script_base_dir

## Signature

`init_script_base_dir(provided_dir=None)`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

Existing arguments, existing task_info/task_id/task_type shapes and script_base_dir.

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

Retain provided_dir/cwd semantics for runtime config/data/log roots, default to the explicit current PROJECT_ROOT; source check is this package canonical pipeline directory.

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

No SQL changes. Existing task state queries and updates remain verbatim. No subprocess executed during static/offline validation.

## Source

`src/kdb/services/off_task/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
