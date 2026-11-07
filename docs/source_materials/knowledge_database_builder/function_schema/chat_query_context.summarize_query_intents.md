# chat_query_context.summarize_query_intents

## 描述
把用户 query 列表聚类为高频业务意图。优先用本地统一 LLM（local_llm_adapter）聚类；LLM 不可用 / 解析失败时退化为基于归一化文本的频次兜底。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| queries | list[str] | 是 | 用户 query 列表 |
| client | str | 是 | 客户名（拼进 prompt） |
| model_name | str\|None | 否 | LLM 模型名 |
| provider | str\|None | 否 | LLM 渠道 |
| max_intents | int | 否 | 最多输出意图数，默认 30 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | [{"intent": str, "sample_queries": [str,...]}]；queries 为空返回 [] |

## 降级策略
- 无法导入 local_llm_adapter / LLM 返回空 / JSON 解析失败 → `_fallback_intents`（频次聚合），不抛异常。

## 依赖
- `commons.local_llm_adapter.request_knowledge_llm`
