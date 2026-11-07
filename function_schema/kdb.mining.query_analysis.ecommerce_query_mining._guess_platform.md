# kdb.mining.query_analysis.ecommerce_query_mining._guess_platform

## Signature

`_guess_platform(text: str, source_customers: str='') -> str`

## Description

基于 query 文本和来源 customer 推断平台范围，输出规范平台名或 `通用电商平台`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | query 文本 |
| source_customers | str | 否 | 逗号分隔来源 customer |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 平台范围 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
