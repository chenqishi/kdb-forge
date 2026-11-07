# ecommerce_query_mining.build_where_clause

## 描述
根据客户、时间、用户和 app_id 过滤条件构造 `data_chat_history` 只读查询的 WHERE 片段与参数。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| customers | list[str] | 是 | `data_chat_history.customer` 白名单，不能为空 |
| start_time | str\|None | 否 | 起始时间，标准 MySQL 时间字符串 |
| end_time | str\|None | 否 | 结束时间，标准 MySQL 时间字符串 |
| users | list[str]\|None | 否 | `data_chat_history.user` 白名单 |
| app_ids | list[str]\|None | 否 | `data_chat_history.app_id` 白名单 |
| require_reply | bool | 否 | 是否要求 `reply_content` 非空 |

## Outputs

| 类型 | 说明 |
|------|------|
| tuple[str, list] | WHERE SQL 字符串和参数列表 |

## SQL

- 表：`data_chat_history`
- 读取过滤字段：`customer`、`send_type`、`create_time`、`user`、`app_id`、`channel_type`、`reply_content`、`msg_id`、`send_content`
- 固定过滤：`send_type='TEXT'`、`send_content IS NOT NULL`、排除 `channel_type='wework_juhe'`、排除常见失败回复。
- 电商业务域过滤在 Python 层通过 `is_business_query` 执行；避免在长文本字段上做 `REGEXP` 导致大表慢查询。
- 不强制过滤 `is_enabled/del_flag`，因为历史聊天表中这两个字段可能为空或未统一维护；该脚本只读，不做状态更新。
- 写操作：无。
- 表结构来源：2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`，字段包含 `customer/send_content/send_type/create_time/reply_content/norm_content/regular_content/content_category/msg_id/app_id/user/channel_type`。
