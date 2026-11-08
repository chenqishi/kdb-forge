# kdb.mining.web.processing.qa_generation.run_batch_clear_html_content

## Signature

`run_batch_clear_html_content(input_file, output_file, process_field_num=-1, flag='', process_field='formatted_text', business_context_path=None, quality_profile='', llm_backend='dify', llm_model_name=None, llm_provider=None)`

## Description

批量处理 HTML 映射文件，抽取 QA 并添加质量等级。新增业务上下文参数；HTML 当前仍使用 Dify，非 dify 后端记录降级。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| input_file | str | 是 | HTML 映射文件 |
| output_file | str | 是 | 输出映射文件 |
| process_field_num | int | 否 | JSON 路径字段位置，默认 -1 |
| flag | str | 否 | 预留标识 |
| process_field | str | 否 | HTML 正文字段 |
| business_context_path | str\|None | 否 | `business_context.json` |
| quality_profile | str | 否 | 质量画像 |
| llm_backend | str | 否 | 当前 HTML Dify 兼容；非 dify 会降级 |
| llm_model_name / llm_provider | str\|None | 否 | 预留透传字段 |

## Outputs

| 产物 | 说明 |
|------|------|
| output_file | 每行追加 QA quality JSON 路径 |
| *_qa_quality.json | `{high, mid, low}` QA 质量文件 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/web/processing/qa_generation.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
