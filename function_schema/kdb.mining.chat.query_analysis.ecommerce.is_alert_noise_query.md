# kdb.mining.chat.query_analysis.ecommerce.is_alert_noise_query

## Signature

`is_alert_noise_query(text: str) -> bool`

## Description

判断最终 query 是否属于告警、通知、消息提醒、系统状态更新等非知识覆盖率测评问题。用于从结果集中剔除“告警信息”类噪声。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 候选或最终 query |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 是否为告警/通知类噪声 |

## SQL

无 SQL。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
