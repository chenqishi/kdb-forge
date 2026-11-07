# ecommerce_query_mining.merge_candidate_stats

## 描述
对 SQL 聚合后的候选再次按 Python 规范化 key 合并，消除不可见字符、大小写和空白差异造成的重复候选。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| candidates | list[dict] | 是 | `fetch_candidate_stats` 规则过滤后的候选 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 合并后按频次倒序排列的候选 |

## SQL

无 SQL。
