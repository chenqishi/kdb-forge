# kdb.mining.chat.query_analysis.ecommerce.build_platform_queries

## Signature

`build_platform_queries(template: str, platforms: Sequence[str]) -> List[dict]`

## Description

把带 `{platform}` 占位符的 `norm_query` 模板按平台名实例化，生成每个平台对应的具体测评 query。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| template | str | 是 | 带 `{platform}` 占位符的 query 模板 |
| platforms | list[str] | 是 | 需要实例化的平台名列表 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 每项包含 `platform` 和实例化后的 `query` |

## SQL

无 SQL。

## Source

`src/kdb/mining/chat/query_analysis/ecommerce.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
