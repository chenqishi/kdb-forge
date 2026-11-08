# kdb.mining.chat.query_analysis.ecommerce.normalize_query_key

## Signature

`normalize_query_key(text: str) -> str`

## Description

为候选 query 生成去重 key，统一大小写、空白、标点和常见平台别名。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 候选 query |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 去重 key |

## SQL

无 SQL。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
