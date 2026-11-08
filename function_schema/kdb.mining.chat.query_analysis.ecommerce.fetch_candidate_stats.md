# kdb.mining.chat.query_analysis.ecommerce.fetch_candidate_stats

## Signature

`fetch_candidate_stats(connector: MySQLConnector, customers: Sequence[str], start_time: Optional[str], end_time: Optional[str], users: Optional[Sequence[str]]=None, app_ids: Optional[Sequence[str]]=None, raw_limit: int=20000, require_reply: bool=True) -> List[dict]`

## Description

从 `data_chat_history` 用 SQL 聚合候选问题，不逐条读取全量消息。优先使用 `regular_content`，其次 `norm_content`，最后 `send_content`，按去重消息数统计频次。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| connector | MySQLConnector | 是 | MySQL 连接器 |
| customers | list[str] | 是 | customer 白名单 |
| start_time | str\|None | 否 | 起始时间 |
| end_time | str\|None | 否 | 结束时间 |
| users | list[str]\|None | 否 | user 白名单 |
| app_ids | list[str]\|None | 否 | app_id 白名单 |
| raw_limit | int | 否 | SQL 聚合后取前 N 个候选 |
| require_reply | bool | 否 | 是否要求已有客服/机器人回复 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 候选统计，含 `source_query/cnt/source_customers/categories/latest_time` |

## SQL

- 表：`data_chat_history`
- 读取字段：`norm_content`、`regular_content`、`send_content`、`msg_id`、`customer`、`content_category`、`create_time`
- 过滤字段来自 `build_where_clause`。
- 聚合：`GROUP BY source_query`，`COUNT(DISTINCT COALESCE(msg_id, id))`。
- 写操作：无。
- 表结构来源：2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
