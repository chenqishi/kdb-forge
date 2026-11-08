# kdb.mining.chat.query_analysis.category_mining.gen_category_from_chat_history

## Signature

`gen_category_from_chat_history(sql_config, client_name, start_time, end_time)`

## Inputs

SQL 配置、客户和起止时间；支持原日期转换。

## Outputs

按群收集消息后交给原类目生成流程；保持读取、分组、清理与外部调用顺序。

## SQL

以下表和字段来自当前函数内实际 SQL，未提供完整 DDL：

```sql
SELECT other_user_nickname, from_user_nickname, send_content, create_time
            FROM data_chat_history
            WHERE customer=%s AND create_time >= %s AND create_time < %s AND send_content IS NOT NULL AND send_content != ''
            ORDER BY other_user_nickname, create_time
```

```sql
SELECT cate1, cate2 FROM data_content_category WHERE client=%s OR client='global_use'
```

```sql
SELECT item_key, item_value FROM rf_app_offline_task WHERE client=%s AND task_type='category_mining'
```

## Source

`src/kdb/mining/chat/query_analysis/category_mining.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
