# kdb.mining.query_analysis.ecommerce_query_mining.is_meaningful_query

## Signature

`is_meaningful_query(text: str) -> bool`

## Description

规则判断文本是否适合作为测评 query 候选，过滤空文本、寒暄、链接、图片、纯表情、过短和明显对话碎片。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 已清洗或原始文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 是否保留为候选 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
