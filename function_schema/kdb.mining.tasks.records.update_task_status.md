# kdb.mining.tasks.records.update_task_status

## Signature

`update_task_status(task_id, run_status, task_stage=None, pid=None)`

## Inputs

task_id、run_status；可选 task_stage、pid。

## Outputs

更新成功 commit 返回 True；无连接或 MySQL Error 返回 False，错误 rollback。task_stage/pid 仅在 truthy 时写入，PID转字符串。

## SQL

按 task_id 更新 rufitai.dops_task_kggen_info：必写 run_status、update_time；可写 task_stage、related_pid。

## Source

`src/kdb/mining/tasks/records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
