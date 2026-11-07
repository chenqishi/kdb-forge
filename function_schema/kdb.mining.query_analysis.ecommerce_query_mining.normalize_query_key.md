# kdb.mining.query_analysis.ecommerce_query_mining.normalize_query_key

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

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
