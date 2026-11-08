# kdb.mining.chat.query_analysis.ecommerce.sanitize_query_text

## Signature

`sanitize_query_text(text: str) -> str`

## Description

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

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
