# kdb.mining.query_analysis.ecommerce_query_mining.normalize_platform_specific_query

## Signature

`normalize_platform_specific_query(text: str) -> str`

## Description

生成平台占位符 query 模板：只把平台名称或泛称“电商平台”替换为 `{platform}`，不强行抹除 FBA、RFC、CG 仓、站点国家、平台字段等真实业务差异。

示例：

- `如何入驻Mercado Libre平台？` -> `如何入驻{platform}平台？`
- `Mercado Libre墨西哥站点的运费计费规则是什么？` -> `{platform}的运费计费规则是什么？`
- `Wayfair平台如何合并SKU？` -> `{platform}平台如何合并SKU？`
- `如何进行商品刊登？` -> `在{platform}平台，如何进行商品刊登？`

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | str | 是 | 原始 query |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 带 `{platform}` 占位符的 `norm_query` 模板 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
