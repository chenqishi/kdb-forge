# kdb.mining.query_analysis.ecommerce_query_mining.merge_candidate_stats

## Signature

`merge_candidate_stats(candidates: Sequence[dict]) -> List[dict]`

## Description

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

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
