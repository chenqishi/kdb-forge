# document_qa_segment_mining.context_enrichment_stages

## 描述
`DocumentQAMiningTaskController` 新增的业务上下文增强相关字段与阶段。所有新增字段缺省时旧流程行为不变。

## 新增 task_info 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| business_context_text | str\|None | None | 前端业务背景文本 |
| knowledge_objective | str\|None | None | 知识目标 |
| quality_profile | str | business_task_knowledge | 质量画像 |
| enable_context_enrichment | bool | False | 上下文增强总开关 |
| enable_chat_query_context | bool | False | 是否查 data_chat_history |
| enable_web_context | bool | False | 是否联网（默认关闭） |
| context_cache_ttl_days | int | 30 | 上下文缓存 TTL |
| business_context_cache_dir | str\|None | data/business_context_cache | 共享缓存目录；用于跨文档/HTML任务复用 query 挖掘结果 |
| llm_backend | str | dify | QA/segment 后端 |
| llm_model_name | str\|None | None | 本地后端模型 |
| llm_provider | str\|None | None | 本地后端渠道 |
| review_only | bool | False | 仅产审核/中间文件，跳过 ES 插入 |

## 新增/修改阶段

| 阶段 | 方法 | 条件 |
|------|------|------|
| 4.5 构建业务上下文 | `stage_4_5_build_business_context` | 仅 enable_context_enrichment=true，否则 no-op |
| 5 QA生成 | `stage_5_generate_qa` | 启用时透传 `_qa_context_cli_args()` |
| 6.5 通用质量后处理 | `stage_6_5_generic_quality` | 仅 enable_context_enrichment=true，否则 no-op |
| 9 段落生成 | `stage_9_generate_segment` | 启用时透传业务上下文/后端参数 |
| 8/11 ES 插入 | — | review_only=true 时从执行计划中剔除 |

## 产物
- `business_context.json`：业务上下文（build_business_context 产物，任务目录内留一份快照）。
- `data/business_context_cache/ctx_<hash>.json`：默认共享缓存；同 client/objective/context-source 且 TTL 未过期时复用，不重复挖 query。
- `generic_quality_report.json`：通用质量后处理修复/拒绝报告。

## SQL
- 间接经 `chat_query_context.load_client_queries` 读取 `data_chat_history`（详见该 schema）。DB 不可用时降级为空意图，不影响主任务。

## 降级
- 上下文构建 / 通用质量后处理失败均返回 True（降级跳过），不中断主任务（已有 dify 质量过滤兜底）。
