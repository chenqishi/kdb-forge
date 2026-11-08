# kdb.mining.web.pipeline.HtmlKgGenTaskController.__init__

## Signature

`__init__(self, script_dir, task_id, task_info)`

## Description

初始化 HTML 知识生成任务控制器。新增可选业务上下文增强字段；字段缺省时旧流程不变。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| script_dir | str | 是 | 项目根目录 |
| task_id | str | 是 | 离线任务 ID |
| task_info | dict | 是 | 任务配置 |

## 新增 task_info 字段

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| business_context_text | str\|None | None | 前端传入业务背景 |
| knowledge_objective | str\|None | None | 本次知识抽取目标，参与缓存 key |
| quality_profile | str | business_task_knowledge | 通用质量画像 |
| enable_context_enrichment | bool | False | 上下文增强总开关 |
| enable_chat_query_context | bool | False | 是否从 data_chat_history 挖掘用户 query 意图 |
| enable_web_context | bool | False | 是否启用网络业务背景 |
| context_cache_ttl_days | int | 30 | 业务上下文缓存 TTL |
| business_context_cache_dir | str\|None | data/business_context_cache | 共享缓存目录；可被任务显式覆盖 |
| llm_backend | str | dify | HTML 当前保留 Dify，非 dify 会记录降级 |
| llm_model_name | str\|None | None | 预留给后端透传 |
| llm_provider | str\|None | None | 预留给后端透传 |
| review_only | bool | False | 跳过 ES 插入，仅产中间文件 |
| insert_is_need_llm | bool\|None | None | QA/segment 入库查重是否调用 LLM 精判；None 沿用索引配置，False 仍保留向量查重 |
| insert_check_duplicate | bool\|None | None | QA/segment 是否执行跨库查重；None 沿用索引配置，False 用于已按来源去重且必须保留独立类目副本的任务 |
| skip_multimodal | bool | False | 跳过图片/OCR阶段，后续直接读取 Firecrawl 文本；`firecrawl_only=true` 时自动启用 |

## Outputs

无显式返回；初始化中间文件路径、增强配置和工具实例。

## SQL

本函数不直接读写 SQL。后续上下文构建阶段可能间接读取 `data_chat_history`。

## Source

`src/kdb/mining/web/pipeline.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
