# kdb.mining.tasks.records.insert_task_record

## Signature

`insert_task_record(task_id, task_type, task_info)`

## Inputs

task_id、五种受支持的 task_type 与实际 task_info；客户和 user 从 task_info 读取，可为空。

## Outputs

插入任务记录并 commit 后返回 True；无连接返回 False，MySQL Error 时 rollback 返回 False，最终释放连接。task_info 按 JSON 序列化，初始 task_stage=未运行、run_status=0、进度/PID为空。

## SQL

写 rufitai.dops_task_kggen_info：task_id、task_type、task_info、task_stage、task_process_rate、run_status、related_pid、client、user、create_time、update_time。

## Source

`src/kdb/mining/tasks/records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
