# kdb.services.off_task.app.reset_task_status

## Signature

`reset_task_status(task_id)`

## Inputs

精确 task_id。

## Outputs

状态重置后 commit 返回 True；无连接或 MySQL Error 返回 False，错误 rollback。

## SQL

按 task_id 更新 rufitai.dops_task_kggen_info：run_status=0、task_stage=未运行、task_process_rate/related_pid为空、update_time=当前时间。

## Source

`src/kdb/services/off_task/app.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
