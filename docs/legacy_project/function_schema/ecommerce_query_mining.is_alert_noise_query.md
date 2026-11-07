# ecommerce_query_mining.is_alert_noise_query

## 描述
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
