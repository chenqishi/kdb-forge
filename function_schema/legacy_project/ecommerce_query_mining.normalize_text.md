# ecommerce_query_mining.normalize_text

## 描述
清洗单条聊天文本，统一空白、去掉引用/链接噪声，并截断超长文本用于后续候选 query 判断。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str\|None | 否 | 原始文本 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 清洗后的文本，无法使用时返回空字符串 |

## SQL

无 SQL。
