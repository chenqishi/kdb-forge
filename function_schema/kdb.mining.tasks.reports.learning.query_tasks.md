# kdb.mining.tasks.reports.learning.query_tasks

## Signature

`query_tasks(mysql_config, start_time, end_time)`

## Inputs

保留参数签名 `mysql_config, start_time, end_time`。输入结构、CLI位置参数与原实现一致。

## Outputs

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.tasks.reports.learning`；全部依赖来自当前 kdb 包。

## SQL / ES

SQL只读：rufitai.dops_task_kggen_info: task_id/task_type/client/user/task_stage/run_status/create_time/update_time/task_result。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## Source

`src/kdb/mining/tasks/reports/learning.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
