# kdb.mining.tasks.records.reset_task_status

## Signature

`reset_task_status(task_id)`

## Inputs

精确 task_id。

## Outputs

状态重置后 commit 返回 True；无连接或 MySQL Error 返回 False，错误 rollback。

## SQL

按 task_id 更新 rufitai.dops_task_kggen_info：run_status=0、task_stage=未运行、task_process_rate/related_pid为空、update_time=当前时间。

## Source

`src/kdb/mining/tasks/records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
