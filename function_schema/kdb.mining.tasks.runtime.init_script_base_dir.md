# kdb.mining.tasks.runtime.init_script_base_dir

## Signature

`init_script_base_dir(provided_dir=None)`

## Inputs


Existing arguments, existing task_info/task_id/task_type shapes and script_base_dir.

## Outputs


Retain provided_dir/cwd semantics for runtime config/data/log roots, default to the explicit current PROJECT_ROOT; source check is this package canonical pipeline directory.

## SQL


No SQL changes. Existing task state queries and updates remain verbatim. No subprocess executed during static/offline validation.

## Source

`src/kdb/mining/tasks/runtime.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
