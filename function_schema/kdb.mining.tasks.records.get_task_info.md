# kdb.mining.tasks.records.get_task_info

## Signature

`get_task_info(task_id)`

## Inputs

精确 task_id。

## Outputs

唯一记录返回字典；task_result 为非空 JSON 时解析，否则为 {}。无连接、无记录、重复记录或 MySQL Error 返回 None。JSONDecodeError 不在 MySQL Error 捕获范围内。

## SQL

只读 rufitai.dops_task_kggen_info：task_id、task_type、task_stage、task_process_rate、run_status、task_result；WHERE task_id=%s。

## Source

`src/kdb/mining/tasks/records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
