# kdb.mining.tasks.submission.chat_batch.BatchChatQARequestRunner._positive_int_env

## Signature

`_positive_int_env(name, default)`

## Inputs

保留参数签名 `name, default`。输入结构、CLI位置参数与原实现一致。

## Outputs

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.tasks.submission.chat_batch`；全部依赖来自当前 kdb 包。

## SQL / ES

本函数无直接 SQL；应用数据由 get_enabled_appids 读取 rufitai.rf_ai_role_config： id/app_id/config_key/config_value/is_enabled/del_flag；rf_app_info: id/customer/application_name/is_enabled/del_flag。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## Source

`src/kdb/mining/tasks/submission/chat_batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
