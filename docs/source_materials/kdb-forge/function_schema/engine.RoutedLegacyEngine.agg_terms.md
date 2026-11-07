# RoutedLegacyEngine.agg_terms

## Inputs
index、query DSL、terms 字段、聚合 size、可选子聚合。
## Outputs
通过 ES8 `search(query=..., aggs=...)` 返回 buckets 列表。
## SQL
无；底层读取 Elasticsearch。
