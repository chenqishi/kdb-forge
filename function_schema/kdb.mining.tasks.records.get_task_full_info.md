# kdb.mining.tasks.records.get_task_full_info

## Signature

`get_task_full_info(task_id)`

## Inputs

精确 task_id。

## Outputs

唯一记录返回完整任务字典；task_info/task_result 缺失或 JSON 无法解析时设为 {}。无连接、无记录、重复记录或 MySQL Error 返回 None。

## SQL

只读 rufitai.dops_task_kggen_info：task_id、task_type、task_info、task_stage、task_process_rate、run_status、related_pid、task_result、client、user；WHERE task_id=%s。

## Source

`src/kdb/mining/tasks/records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
