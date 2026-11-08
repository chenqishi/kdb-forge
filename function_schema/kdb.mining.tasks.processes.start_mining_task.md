# kdb.mining.tasks.processes.start_mining_task

## Signature

`start_mining_task(task_type, task_info, task_id)`

## Inputs


Existing arguments, existing task_info/task_id/task_type shapes and script_base_dir.

## Outputs


Preserve existing task-type mapping, task JSON, task-id, --script-dir, cwd, logging, PID/error handling and Popen timing. Execute sys.executable -m the corresponding kdb.entrypoints.cli.mining module. Source check uses project/src canonical pipeline file; child env is subprocess_env() retaining inherited variables and adding only project/src.

## SQL


No SQL changes. Existing task state queries and updates remain verbatim. No subprocess executed during static/offline validation.

## Source

`src/kdb/mining/tasks/processes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
