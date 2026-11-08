# kdb.mining.chat.query_analysis.ecommerce.is_business_query

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
