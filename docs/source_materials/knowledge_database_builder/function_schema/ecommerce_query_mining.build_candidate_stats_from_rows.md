# ecommerce_query_mining.build_candidate_stats_from_rows

## 描述
基于本地随机样本构造候选 query 统计，优先使用 `regular_content`、其次 `norm_content`、最后 `send_content`，在 Python 层过滤业务域和噪声后合并计数。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rows | list[dict] | 是 | 本地聊天样本 |
| max_candidates | int | 否 | 最多返回候选数 |
| sample_per_query | int | 否 | 每个候选保留的原始样本数量 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 候选统计，含 source_query/cnt/source_customers/categories/latest_time/samples |

## SQL

无 SQL。
