# kdb.mining.query_analysis.ecommerce_query_mining.fallback_generalize_batch

## Signature

`fallback_generalize_batch(candidates: Sequence[dict]) -> List[dict]`

## Description

LLM 不可用时，把候选 query 规则化成可用于测评的通用 query，并补充主题、优先级等字段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| candidates | list[dict] | 是 | 候选统计和样本 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 通用 query 记录 |

## SQL

无 SQL。

## Source

`src/kdb/mining/query_analysis/ecommerce_query_mining.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
