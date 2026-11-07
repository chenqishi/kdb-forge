# kdb.jobs.chat_mining.BatchChatQARequestRunner.get_default_start_time

## Signature

`BatchChatQARequestRunner.get_default_start_time(self)`

## Inputs

保留参数签名 `self`。获取默认开始时间（一个月前）

## Outputs

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.jobs.chat_mining`；全部依赖来自当前 kdb 包。

## SQL / ES

本函数无直接 SQL；应用数据由 get_enabled_appids 读取 rufitai.rf_ai_role_config： id/app_id/config_key/config_value/is_enabled/del_flag；rf_app_info: id/customer/application_name/is_enabled/del_flag。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## Source

`src/kdb/jobs/chat_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
