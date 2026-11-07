# kdb.reporting.csat.csat_data_query.query_csat_sessions

## Signature

`query_csat_sessions(mysql_connector, start_time, end_time, channel_type, client, include_chat_detail=False)`

## Inputs

已配置 MySQLConnector；start_time、end_time、channel_type、client；可选 include_chat_detail=False。

## Outputs

返回满意度记录列表，按问卷与会话消息窗口分组；字段含 survey_instance_id、query_session_id、account_id、session_create_datetime、escalated、escalation_datetime、satisfaction。include_chat_detail 时追加 sender_name/sender_id/content/mess_type/create_time 明细。无问卷返回 []，数据库异常交给调用方处理。

## SQL

只读 data_csat_result：survey_instance_id、robot_id、session_id、reply_result、create_time、account_id；按 create_time 闭区间、channel_type、client 过滤，并查每 session 窗口前最近问卷时间。只读 data_online_sessions：session_id、sender_name、sender_id、mess_type、mess_data_type、content、create_time；按 session_id、channel 和 IFNULL(del_flag,0)!=1 过滤，按会话/时间排序。

## Source

`src/kdb/reporting/csat/csat_data_query.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
