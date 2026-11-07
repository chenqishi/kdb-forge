# kdb.mining.generation.builders.knowlege_segment_builder_by_dify.run_batch_get_segment_knowledge_html_json

## Signature

`run_batch_get_segment_knowledge_html_json(html_json_batch_file, flag='', platform_field_num=None, filed_num=-1, process_field_key='formatted_text', is_direct_output=0, use_image_content=0, business_context_path=None, quality_profile='', llm_backend='dify', llm_model_name=None, llm_provider=None)`

## Description

批量生成 HTML segment 知识。新增业务上下文参数，与文档任务复用同一个 `business_context.json`；HTML 当前仍使用 Dify，非 dify 后端记录降级。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| html_json_batch_file | str | 是 | HTML 映射文件 |
| flag | str | 否 | 输出标识 |
| platform_field_num | int\|None | 否 | 平台字段位置 |
| filed_num | int | 否 | HTML JSON 路径字段位置 |
| process_field_key | str | 否 | 正文字段 |
| is_direct_output | int | 否 | 保留参数 |
| use_image_content | int | 否 | 保留参数 |
| business_context_path | str\|None | 否 | `business_context.json` |
| quality_profile | str | 否 | 质量画像 |
| llm_backend | str | 否 | 当前 HTML Dify 兼容；非 dify 会降级 |
| llm_model_name / llm_provider | str\|None | 否 | 预留透传字段 |

## Outputs

| 类型 | 说明 |
|------|------|
| stdout | 每行一个 HTML segment JSON |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/generation/builders/knowlege_segment_builder_by_dify.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
