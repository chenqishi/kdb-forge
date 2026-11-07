# kdb.mining.query_analysis.ecommerce_query_mining.extract_platform_names_for_query

## Signature

`extract_platform_names_for_query(text: str, source_customers: str='', platform_scope: str='') -> List[str]`

## Description

从 `source_customers`、`platform_scope` 和 query 文本中提取用于实例化 `{platform}` 占位符的平台名。优先识别美客多站点级平台，例如 `美客多墨西哥站点`；其次使用来源 customer，避免把 Wayfair 专属问题因为文本中出现 Amazon 等生态词而错误扩展到其它平台。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 原始 query |
| source_customers | str | 否 | 逗号分隔的来源 customer，例如 `mercado,wayfair` |
| platform_scope | str | 否 | LLM 或规则给出的平台范围 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[str] | 平台展示名列表，例如 `["美客多墨西哥站点"]`、`["美客多平台"]`、`["Wayfair"]` |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
