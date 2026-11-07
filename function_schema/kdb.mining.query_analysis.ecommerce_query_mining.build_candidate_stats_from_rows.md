# kdb.mining.query_analysis.ecommerce_query_mining.build_candidate_stats_from_rows

## Signature

`build_candidate_stats_from_rows(rows: Sequence[dict], max_candidates: int=1000, sample_per_query: int=2) -> List[dict]`

## Description

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

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
