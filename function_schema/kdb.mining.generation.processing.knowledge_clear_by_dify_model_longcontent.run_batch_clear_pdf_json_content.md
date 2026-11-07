# kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent.run_batch_clear_pdf_json_content

## Signature

`run_batch_clear_pdf_json_content(pdf_json_batch_file, flag='', from_file_name_field_num=0, use_image_content=0, business_context_path=None, quality_profile='', llm_backend='dify', llm_model_name=None, llm_provider=None, image_placeholder=1)`

## Description

批量处理 PDF JSON 文件生成 QA 并添加质量信息。可选参数支持业务上下文增强与本地 LLM 后端；Dify 后端内置长文硬分段保护。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| pdf_json_batch_file | str | 是 | 批处理映射文件 |
| flag | str | 否 | 输出文件名标志（通常 task_id） |
| from_file_name_field_num | int | 否 | 文件名字段位置，默认 0 |
| use_image_content | int | 否 | 是否用图片内容，默认 0 |
| business_context_path | str\|None | 否 | 业务上下文 JSON；仅内容有效时增强 prompt（local 后端） |
| quality_profile | str | 否 | 质量画像，透传本地后端 prompt |
| llm_backend | str | 否 | dify（默认，旧行为不变）/local_llm/auto |
| llm_model_name | str\|None | 否 | 本地后端模型名 |
| llm_provider | str\|None | 否 | 本地后端渠道 |

## Outputs

| 类型 | 说明 |
|------|------|
| stdout | 每个文件追加 file_path/all_content_file/add_quality_file 字段并打印；add_quality_file 为 {high,mid,low} 结构 |

## 后端行为

- `dify`（默认）：调用 `clear_pdf_json_content` + `add_quality_info_to_qa_json`；长文会先按页硬分段，避免 Dify `paragraph` 输入超限。
- `local_llm`：`clear_pdf_json_content_local`（业务上下文 system prompt + agents LLM），`mark_local_qa_quality` 标质量；无输出时写空 {high,mid,low}。
- `auto`：local 优先，无输出/异常回退 dify。

## 兼容

- 不传 business_context_path 且 llm_backend=dify → 接口参数兼容旧版；长文处理会新增硬分段保护，因此输出可能因窗口化而与旧版略有差异。

## 依赖

- `load_business_context` / `clear_pdf_json_content_local` / `mark_local_qa_quality`
- `kdb.shared.clients.local_llm_adapter.request_knowledge_llm`

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/mining/generation/processing/knowledge_clear_by_dify_model_longcontent.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
