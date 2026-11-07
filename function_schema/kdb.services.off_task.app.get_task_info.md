# kdb.services.off_task.app.get_task_info

## Signature

`get_task_info(task_id)`

## Inputs

精确 task_id。

## Outputs

唯一记录返回字典；task_result 为非空 JSON 时解析，否则为 {}。无连接、无记录、重复记录或 MySQL Error 返回 None。JSONDecodeError 不在 MySQL Error 捕获范围内。

## SQL

只读 rufitai.dops_task_kggen_info：task_id、task_type、task_stage、task_process_rate、run_status、task_result；WHERE task_id=%s。

## Source

`src/kdb/services/off_task/app.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
