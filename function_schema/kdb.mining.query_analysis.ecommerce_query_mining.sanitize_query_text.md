# kdb.mining.query_analysis.ecommerce_query_mining.sanitize_query_text

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

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
