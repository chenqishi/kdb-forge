# ecommerce_query_mining.fallback_generalize_batch

## 描述
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
