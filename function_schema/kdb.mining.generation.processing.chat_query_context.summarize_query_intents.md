# kdb.mining.generation.processing.chat_query_context.summarize_query_intents

## Signature

`summarize_query_intents(queries: List[str], *, client: str, model_name: Optional[str]=None, provider: Optional[str]=None, max_intents: int=30) -> List[dict]`

## Inputs

Existing function signature and business inputs are unchanged. Read together with the pre-existing function contract indexed by its original source prefix.

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| queries | list[str] | 是 | 用户 query 列表 |
| client | str | 是 | 客户名（拼进 prompt） |
| model_name | str\|None | 否 | LLM 模型名 |
| provider | str\|None | 否 | LLM 渠道 |
| max_intents | int | 否 | 最多输出意图数，默认 30 |

## Outputs

Only dependency imports and canonical project/source/resource locations change. Runtime interfaces, business request parameters, output data, error/exit behavior and initialization timing remain those of the existing implementation. Service task launch and optional LLM plugin details are defined in off_task_app.* and local_llm_adapter.* contracts.

| 类型 | 说明 |
|------|------|
| list[dict] | [{"intent": str, "sample_queries": [str,...]}]；queries 为空返回 [] |

## SQL

No query, field, table, scoring or data mutation change. No backend or subprocess was kdb.mining.generation.run during migration validation.

## Description

把用户 query 列表聚类为高频业务意图。优先用本地统一 LLM（local_llm_adapter）聚类；LLM 不可用 / 解析失败时退化为基于归一化文本的频次兜底。

## 降级策略

- 无法导入 local_llm_adapter / LLM 返回空 / JSON 解析失败 → `_fallback_intents`（频次聚合），不抛异常。

## 依赖

- `kdb.shared.clients.local_llm_adapter.request_knowledge_llm`

## Source

`src/kdb/mining/generation/processing/chat_query_context.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
