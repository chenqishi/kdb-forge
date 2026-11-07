# kdb.mining.generation.builders.knowlege_segment_builder_by_dify.run_batch_get_segment_knowledge

## Signature

`run_batch_get_segment_knowledge(pdf_json_batch_file, flag='', from_file_name_field_num=0, platform_field_num=None, is_direct_output=0, use_image_content=0, business_context_path=None, quality_profile='', llm_backend='dify', llm_model_name=None, llm_provider=None, index_workers=1)`

## Description

批量生成 segment 知识。新增可选业务上下文/后端参数；不传时行为与旧流程一致（Dify 后端）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pdf_json_batch_file | str | 是 | 批处理映射文件 |
| flag | str | 否 | 输出文件名标志 |
| from_file_name_field_num | int | 否 | 文件名字段位置，默认 0 |
| platform_field_num | int\|None | 否 | platform 字段位置 |
| is_direct_output | int | 否 | 1=逐行打印 segment JSON 到 stdout |
| use_image_content | int | 否 | 是否用图片内容 |
| business_context_path | str\|None | 否 | 业务上下文 JSON；仅 local 后端用于增强 prompt |
| quality_profile | str | 否 | 质量画像（预留） |
| llm_backend | str | 否 | dify（默认）/local_llm/auto |
| llm_model_name | str\|None | 否 | 本地后端模型 |
| llm_provider | str\|None | 否 | 本地后端渠道 |

## 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| segment_dify_max_retries | 1 | segment_generation 使用 Dify 后端时的最大重试次数 |
| segment_dify_timeout | 180 | segment_generation 使用 Dify 后端时的单次 blocking 请求超时秒数 |

## Outputs

| 类型 | 说明 |
|------|------|
| stdout/文件 | segment_info JSON（含 keywords/phrases/topics/content/from_file_name/index_file_name/pages） |

## 后端行为

- `dify`（默认）：`get_segment_knowledge_by_dify`。长文先按页硬分段（默认 ≤40 页/80000 字符）再语义分段，调用索引模型前再限制 ≤10 页/30000 字符，避免整篇文档超过 Dify paragraph 限制。该阶段默认使用较短 Dify timeout 和 1 次重试，避免单个子段阻塞整批任务过久。
- `local_llm`：`get_segment_knowledge_by_local_llm` —— 业务上下文 system prompt，拆分自包含主题段（不整篇灌入，标题自包含），输出与 dify 兼容的 segment_info（content 为单页 {"1":[{type:text,text_content}]}）。
- `auto`：local 优先，无输出/异常回退 dify。

## 兼容

- content 字段保持 page-dict 结构，确保 `kdb.mining.transformations.schema_trans.trans_doc_segment_to_search_data` 正常转换。

## 依赖

- `load_segment_business_context` / `get_segment_knowledge_by_local_llm`
- `kdb.shared.clients.local_llm_adapter.request_knowledge_llm`

## 单文件失败隔离（2026-09-02 补）

`get_segment_knowledge_by_dify` 的调用包在 try/except 里：单个文件失败只记 error
并 `continue`，不再中断整批。

这是必需的：wayfair 任务 74256b78 两次重跑分别因 `KeyError: '8'`（旧兜底页码逻辑）
和 `ValueError: inputs is empt`（空段落）在第 21 / 第 7 个文件处整批退出，
导致 235 个文件一条 segment 都没产出，而阶段日志只有一行 ERROR、任务状态照报成功。

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/mining/generation/builders/knowlege_segment_builder_by_dify.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
