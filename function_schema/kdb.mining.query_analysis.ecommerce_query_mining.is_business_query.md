# kdb.mining.query_analysis.ecommerce_query_mining.is_business_query

## Signature

`is_business_query(text: str) -> bool`

## Description

判断文本是否与电商平台入驻、开店、资质、商品、运营、订单、物流、费用、广告、收款等业务覆盖率测评相关。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 已通过基础清洗的候选文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 是否命中电商入驻/运营业务域 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
