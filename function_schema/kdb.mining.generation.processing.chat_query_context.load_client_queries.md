# kdb.mining.generation.processing.chat_query_context.load_client_queries

## Signature

`load_client_queries(*, client: str, admin_user_id: Optional[str]=None, app_id: Optional[str]=None, days: int=180, limit: int=1000, mysql_config_path: Optional[str]=None) -> List[str]`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| client | str | 是 | 客户名（对应 data_chat_history.customer） |
| admin_user_id | str\|None | 否 | 预留过滤维度（当前表无对应列时忽略） |
| app_id | str\|None | 否 | 预留过滤维度 |
| days | int | 否 | 取最近多少天，默认 180 |
| limit | int | 否 | 最多取多少条原始消息，默认 1000 |
| mysql_config_path | str\|None | 否 | mysql 配置路径，缺省自动定位 config/mysql_conn_config.json |

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

| 类型 | 说明 |
|------|------|
| list[str] | 清洗去重后的用户 query；不可用时为空列表 |

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

- 表：`data_chat_history`
- 读取字段：`send_content`（用户消息文本）
- 过滤条件：`customer = %s AND send_type = 'TEXT' AND create_time >= (NOW() - INTERVAL %s DAY)`
- 排序/限制：`ORDER BY create_time DESC LIMIT %s`
- 表结构来源：参考 `src/kdb/reporting/stat_chat_distribution.py`（customer=客户列、send_content=问题文本、send_type=TEXT、create_time=时间、content_category=类别）。
- 写操作：无（只读）。

## Description

从 `data_chat_history` 查询同 client 的真实用户文本问题，清洗（去图片链接、纯表情、寒暄、过短、重复）后返回 query 列表。仅用于校准抽取方向，不直接生成知识。

## 降级策略

- mysql 配置缺失 / 连接失败 / 列名不符 / 任意异常 → 返回 `[]`，记录 warning，绝不抛出中断主任务。
- client 为空 → 返回 `[]`。

## 清洗规则

- 丢弃：空文本、长度<4、含 http/图片后缀、纯符号/表情、纯寒暄词、重复（按 lower 去重）。

## Source

`src/kdb/mining/generation/processing/chat_query_context.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
