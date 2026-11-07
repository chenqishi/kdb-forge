# ecommerce_query_mining.is_meaningful_query

## 描述
规则判断文本是否适合作为测评 query 候选，过滤空文本、寒暄、链接、图片、纯表情、过短和明显对话碎片。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 已清洗或原始文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 是否保留为候选 |

## SQL

无 SQL。
