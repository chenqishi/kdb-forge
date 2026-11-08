# kdb.mining.common.context.business.build_business_context

## Signature

`build_business_context(*, client: str, knowledge_objective: Optional[str], business_context_text: Optional[str], enable_context_enrichment: bool, enable_chat_query_context: bool, enable_web_context: bool, cache_dir: str, ttl_days: int=30, task_info: Optional[dict]=None, now_ts: Optional[float]=None) -> dict`

## Inputs


| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| client | str | 是 | 客户名 |
| knowledge_objective | str\|None | 否 | 本次知识目标，参与缓存 key |
| business_context_text | str\|None | 否 | 前端/任务传入业务背景（最高优先级） |
| enable_context_enrichment | bool | 是 | 总开关；False 返回 enabled=False 最小结构 |
| enable_chat_query_context | bool | 是 | 是否从 data_chat_history 提炼意图 |
| enable_web_context | bool | 是 | 是否启用网络业务背景（默认应 False） |
| cache_dir | str | 是 | 缓存目录 |
| ttl_days | int | 否 | 缓存有效期，默认 30 |
| task_info | dict\|None | 否 | 原始 task，用于读取 llm_model_name/llm_provider/admin_user_id/app_id；可用 `chat_query_exclude_terms`（字符串列表或逗号字符串）过滤明确串站 query |
| now_ts | float\|None | 否 | 时间戳注入（测试用） |

## Outputs


| 字段 | 类型 | 说明 |
|------|------|------|
| enabled | bool | 是否启用增强 |
| context_text | str | 最终给 LLM 的业务背景文本 |
| query_intents | list[dict] | [{intent, sample_queries}] |
| business_boundaries | dict | {keep:[], reject:[]} |
| sources | dict | {frontend_context, chat_history, existing_knowledge, web_search} |
| cache_hit | bool | 是否命中缓存 |
| cache_path | str | 缓存文件路径 |

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Description

通用业务上下文构建与缓存。合并「前端业务背景文本 + data_chat_history 用户高频意图 +（可选）网络业务背景」为给 LLM 的业务背景与抽取方向，按 client+knowledge_objective+来源 hash 缓存。所有子来源均可选且优雅降级。

## 逻辑

1. enable_context_enrichment=false → 直接返回 enabled=False（不查库、不联网、不改 prompt）。
2. 命中未过期缓存则返回。
3. enable_chat_query_context=true → load_client_queries；按 `chat_query_exclude_terms` 过滤后再 summarize_query_intents。过滤词进入缓存 key，避免复用未过滤上下文。
4. enable_web_context=true → build_web_business_context。
5. 渲染 context_text，写缓存。

## 兼容/降级

- 任一子来源异常都被捕获并降级（query_intents 空 / web_text 空），不中断主任务。

## 依赖函数

- `chat_query_context.load_client_queries` / `summarize_query_intents`
- `web_business_context.build_web_business_context`

## Source

`src/kdb/mining/common/context/business.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
