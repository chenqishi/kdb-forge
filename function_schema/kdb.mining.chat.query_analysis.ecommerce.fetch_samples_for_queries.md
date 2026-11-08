# kdb.mining.chat.query_analysis.ecommerce.fetch_samples_for_queries

## Signature

`fetch_samples_for_queries(connector: MySQLConnector, source_queries: Sequence[str], customers: Sequence[str], start_time: Optional[str], end_time: Optional[str], users: Optional[Sequence[str]]=None, app_ids: Optional[Sequence[str]]=None, per_query: int=2, require_reply: bool=True) -> Dict[str, List[dict]]`

## Description

为候选 query 拉取少量原始 `send_content/reply_content` 样本，便于审计和 LLM 泛化时参考上下文。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| connector | MySQLConnector | 是 | MySQL 连接器 |
| source_queries | list[str] | 是 | 候选聚合 query |
| customers | list[str] | 是 | customer 白名单 |
| start_time | str\|None | 否 | 起始时间 |
| end_time | str\|None | 否 | 结束时间 |
| users | list[str]\|None | 否 | user 白名单 |
| app_ids | list[str]\|None | 否 | app_id 白名单 |
| per_query | int | 否 | 每个候选最多样本数 |
| require_reply | bool | 否 | 是否要求回复非空 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict[str, list[dict]] | `source_query -> samples`，样本含原问题、回复片段、客户、类目、时间 |

## SQL

- 表：`data_chat_history`
- 读取字段：`send_content`、`reply_content`、`customer`、`content_category`、`create_time`、`norm_content`、`regular_content`
- 过滤字段来自 `build_where_clause`，额外过滤 `COALESCE(norm_content, regular_content, send_content) IN (...)`。
- 写操作：无。
- 表结构来源：2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
