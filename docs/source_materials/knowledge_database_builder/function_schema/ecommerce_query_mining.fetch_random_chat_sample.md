# ecommerce_query_mining.fetch_random_chat_sample

## 描述
从 `data_chat_history` 为指定 customer 随机抽取文本聊天记录并下载到内存，用于一次性落本地样本文件。该函数只读数据库，不做聚合、不写库。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| connector | MySQLConnector | 是 | MySQL 连接器 |
| customers | list[str] | 是 | customer 列表 |
| sample_size | int | 是 | 总抽样条数 |
| start_time | str\|None | 否 | 起始时间 |
| end_time | str\|None | 否 | 结束时间 |
| users | list[str]\|None | 否 | user 白名单 |
| app_ids | list[str]\|None | 否 | app_id 白名单 |
| require_reply | bool | 否 | 是否要求 `reply_content` 非空 |
| per_customer_even | bool | 否 | 是否按 customer 均分样本数，默认 True |
| random_seed | int\|None | 否 | 记录到元数据的随机种子；MySQL `RAND(seed)` 使用 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 随机样本记录，字段含 id/customer/send_content/reply_content/norm_content/regular_content/content_category/create_time 等 |

## SQL

- 表：`data_chat_history`
- 读取字段：`id`、`customer`、`user`、`app_id`、`send_type`、`send_content`、`reply_content`、`msg_id`、`content_category`、`norm_content`、`regular_content`、`create_time`、`channel_type`
- 过滤字段来自 `build_where_clause`。
- 随机抽样：每个 customer 执行 `ORDER BY RAND()` 或 `ORDER BY RAND(seed)` 后 `LIMIT`。
- 写操作：无。
- 表结构来源：2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`。
