# kdb.mining.tasks.task_status_updater.TaskStatusUpdater._update_task_status

## Signature

`TaskStatusUpdater._update_task_status(self, task_id, run_status=None, task_stage=None, task_result=None, predict_credits=None, actual_credits=None)`

## Inputs

task_id；可选 run_status、task_stage、task_result、predict_credits、actual_credits。仅非 None 字段进入更新。

## Outputs

无字段需更新时返回 True；执行成功 commit 返回 True。无连接或 MySQL Error 返回 False，错误 rollback，最终关闭连接。零值与空串属于显式更新。

## SQL

按 task_id 更新 rufitai.dops_task_kggen_info：run_status、task_stage、task_result、predict_credits、actual_credits 中非 None 字段，并始终写 update_time。

## Source

`src/kdb/mining/tasks/task_status_updater.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
