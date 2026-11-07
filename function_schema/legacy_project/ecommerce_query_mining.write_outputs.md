# ecommerce_query_mining.write_outputs

## 描述
把候选统计、最终 query 集合和摘要报告写入输出目录。最终 query CSV/JSONL 包含原始 `query`、带 `{platform}` 占位符的 `norm_query`、`target_platforms` 和按平台实例化后的 `platform_queries`。同时额外输出一份按平台展开的一行一 query 文件。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| output_dir | str | 是 | 输出目录 |
| candidates | list[dict] | 是 | 规则过滤后的候选 |
| records | list[dict] | 是 | 最终 query 集合 |
| metadata | dict | 是 | 运行参数和统计信息 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | 写出的文件路径，含 `candidates_csv/queries_csv/queries_by_platform_csv/queries_jsonl/report_md` |

## 输出字段

- `coverage_queries.csv` 字段包含：`query`、`norm_query`、`target_platforms`、`platform_queries`、`theme`、`subtheme`、`platform_scope`、`priority`、`evidence_count`、`source_customers`、`categories`、`source_queries`、`sample_queries`、`reason`。
- `coverage_queries_by_platform.csv` 字段包含：`platform`、`query`、`norm_query`、`source_query`、`theme`、`subtheme`、`priority`、`evidence_count`、`source_customers`、`categories`、`reason`。

## SQL

无 SQL。
