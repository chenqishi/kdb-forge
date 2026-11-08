# kdb.mining.common.context.chat_intents.summarize_query_intents

## Signature

`summarize_query_intents(queries: List[str], *, client: str, model_name: Optional[str]=None, provider: Optional[str]=None, max_intents: int=30) -> List[dict]`

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

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Description

把用户 query 列表聚类为高频业务意图。优先用本地统一 LLM（local_llm_adapter）聚类；LLM 不可用 / 解析失败时退化为基于归一化文本的频次兜底。

## 降级策略

- 无法导入 local_llm_adapter / LLM 返回空 / JSON 解析失败 → `_fallback_intents`（频次聚合），不抛异常。

## 依赖

- `kdb.shared.clients.local_llm_adapter.request_knowledge_llm`

## Source

`src/kdb/mining/common/context/chat_intents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
