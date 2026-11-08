# kdb.mining.chat.query_analysis.ecommerce.is_noise_text

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

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
