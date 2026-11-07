# kdb.mining.query_analysis.ecommerce_query_mining.is_noise_text

## Signature

`is_noise_text(text: str) -> bool`

## Description

识别不适合作为电商平台知识覆盖率测评 query 的噪声文本，例如企业微信客服提示、卖群/加微信广告、联系人提醒、纯 @ 助手等。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 候选文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 是否为噪声 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
