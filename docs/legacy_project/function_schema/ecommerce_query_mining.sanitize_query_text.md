# ecommerce_query_mining.sanitize_query_text

## 描述
清理最终 query 中不适合进入测评集的聊天痕迹，例如 `@某某助手`、邮箱、长数字订单号/店铺 ID、多余空白和重复问号。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | LLM 或规则泛化后的 query |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 清理后的 query；无法保留时返回空字符串 |

## SQL

无 SQL。
