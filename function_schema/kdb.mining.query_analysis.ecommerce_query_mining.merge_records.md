# kdb.mining.query_analysis.ecommerce_query_mining.merge_records

## Signature

`merge_records(records: Sequence[dict], max_queries: int=1000, per_theme_limit: int=0) -> List[dict]`

## Description

合并多个批次输出的 query，按规范化 key 去重，累加证据量和来源样本，并按主题/优先级排序；同时过滤告警/通知类噪声，补充带 `{platform}` 占位符的 `norm_query`，并根据来源平台生成 `target_platforms/platform_queries`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| records | list[dict] | 是 | 批次输出记录 |
| max_queries | int | 否 | 最终最多输出条数 |
| per_theme_limit | int | 否 | 每个主题最多保留条数，0 表示不限制 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 去重排序后的 query 集合，每项包含 `query`、`norm_query`、`target_platforms`、`platform_queries` |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
