# kdb.jobs.reports.parse_task_result

## Signature

`parse_task_result(raw_value)`

## Inputs

保留参数签名 `raw_value`。输入结构、CLI位置参数与原实现一致。

## Outputs

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.jobs.reports`；全部依赖来自当前 kdb 包。

## SQL / ES

本函数无直接 SQL；任务数据由 query_tasks 读取 rufitai.dops_task_kggen_info： task_id/task_type/client/user/task_stage/run_status/create_time/update_time/task_result。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## Source

`src/kdb/jobs/reports.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
