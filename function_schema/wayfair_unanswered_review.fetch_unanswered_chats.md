# wayfair_unanswered_review.fetch_unanswered_chats

## 描述
从 `data_chat_history` 捞取 Wayfair 客户下「机器人明确表示无法回答」的对话记录，抽出用户 query。
兜底话术以 `config/wayfair_fallback_patterns.json` 的 `fallback_patterns` 为准（默认包含
「抱歉，目前我无法回答这个问题，建议您优先咨询账号经理或者是desk团队」及邮箱 `support@example.invalid`）。
匹配在 SQL 层用 `reply_content LIKE` 完成（前缀/邮箱是短特征串，不用 REGEXP，避免大表慢查询）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| mysql_config_path | str | 是 | MySQL 配置路径，默认 `config/mysql_conn_config.json` |
| customers | list[str] | 是 | `data_chat_history.customer` 白名单，默认 `["wayfair"]` |
| start_time | str\|None | 否 | 起始时间（含），标准 MySQL 时间字符串 |
| end_time | str\|None | 否 | 结束时间（不含） |
| fallback_patterns | list[str] | 是 | 兜底话术片段，任一命中即算未答 |
| limit | int\|None | 否 | 最多返回条数，None 为不限 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 每条含 `id/customer/send_content/reply_content/msg_id/create_time/norm_content/regular_content/channel_type` |

## SQL

- 表：`data_chat_history`（只读）
- 读取字段：`id`、`customer`、`user`、`app_id`、`send_type`、`send_content`、`reply_content`、`msg_id`、`content_category`、`norm_content`、`regular_content`、`create_time`、`channel_type`
- 固定过滤：`send_type='TEXT'`、`send_content IS NOT NULL AND send_content != ''`、排除 `channel_type='wework_juhe'`
- 未答过滤：`(reply_content LIKE %pattern1% OR reply_content LIKE %pattern2% ...)`
- 写操作：无
- 表结构来源：`function_schema/ecommerce_query_mining.build_where_clause.md`（2026-07-19 只读 `SHOW COLUMNS FROM data_chat_history`）

## 相关

抽 query 用 `pick_query_text`，内部调 `clean_query_text` 剥群聊 @ 噪声
（见 `wayfair_unanswered_review.clean_query_text.md`）；某字段清洗后为空时回退下一个字段。


## Migration provenance and compatibility pointer

Canonical implementation: `src/kdb/mining/query_analysis/wayfair_unanswered_review.py`. Legacy wrapper: `query_understanding_analysis/wayfair_unanswered_review.py`; both resolve to the same migrated implementation.

Source contract preserved from `function_schema/legacy_project/wayfair_unanswered_review.fetch_unanswered_chats.md` (SHA256 `4bc7e7ceb6439db1a088834a449da5a0c41cc0fbe211180b2afcded797d0c359`). That original contains the historical contact example and remains locally retained and ignored. This versionable contract replaces only that contact with a synthetic `.invalid` example; SQL tables/fields, SQL snippets, signatures, input/output format and business rules are unchanged.

The original table-schema source reference is retained above. The migrated historical source is `function_schema/legacy_project/ecommerce_query_mining.build_where_clause.md` (present).
