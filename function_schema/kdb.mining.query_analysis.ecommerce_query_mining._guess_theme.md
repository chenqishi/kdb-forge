# kdb.mining.query_analysis.ecommerce_query_mining._guess_theme

## Signature

`_guess_theme(text: str) -> str`

## Description

基于关键词把 query 粗分到电商平台测评主题，例如入驻开店、账号资质、商品刊登、订单物流等。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 候选或泛化后的 query |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 主题名称，未命中时返回 `其它运营问题` |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
