# ecommerce_query_mining.llm_generalize_batch

## 描述
调用低成本 LLM 将聊天候选问题泛化为自包含、可测评的电商平台通用 query。LLM 失败或解析失败时降级到 `fallback_generalize_batch`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| candidates | list[dict] | 是 | 候选统计和样本 |
| model_name | str\|None | 否 | 模型名 |
| provider | str\|None | 否 | LLM 渠道 |
| batch_index | int | 否 | 当前批次编号，用于日志 |
| skip_llm | bool | 否 | 是否跳过 LLM |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 通用 query 记录，字段含 `query/theme/subtheme/priority/evidence_count/source_queries/reason` |

## SQL

无 SQL。外部接口：通过 `commons.local_llm_adapter.request_knowledge_llm` 调用统一 LLM；调用失败必须降级。
