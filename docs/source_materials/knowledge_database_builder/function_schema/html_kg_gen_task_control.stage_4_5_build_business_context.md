# html_kg_gen_task_control.stage_4_5_build_business_context

## 描述
HTML 任务阶段 4.5：复用 `business_context_builder.build_business_context` 构建业务上下文。`enable_context_enrichment=false` 时 no-op。

## Inputs
无显式参数，读取 `self.task_info` 和初始化字段：

| 字段 | 说明 |
|------|------|
| client / knowledge_objective / business_context_text | 缓存 key 与上下文文本来源 |
| enable_context_enrichment / enable_chat_query_context / enable_web_context | 控制上下文来源 |
| business_context_cache_dir / context_cache_ttl_days | 共享缓存位置与 TTL |

## Outputs

| 产物 | 说明 |
|------|------|
| self.business_context_path | 写入 `business_context.json`，后续 QA/segment/quality 使用 |
| bool | 总是尽量返回 True；增强失败时降级跳过 |

## SQL
本函数不直接读写 SQL；当启用 `enable_chat_query_context` 时，间接通过 `chat_query_context.load_client_queries` 读取 `data_chat_history`。
