# kdb.mining.chat.query_analysis.ecommerce._guess_platform

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
