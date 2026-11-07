# kdb.services.off_task.app.update_task_status

## Signature

`update_task_status(task_id, run_status, task_stage=None, pid=None)`

## Inputs

task_id、run_status；可选 task_stage、pid。

## Outputs

更新成功 commit 返回 True；无连接或 MySQL Error 返回 False，错误 rollback。task_stage/pid 仅在 truthy 时写入，PID转字符串。

## SQL

按 task_id 更新 rufitai.dops_task_kggen_info：必写 run_status、update_time；可写 task_stage、related_pid。

## Source

`src/kdb/services/off_task/app.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
