# kdb.mining.web.processing.qa_generation.process_content

## Signature

`process_content(formatted_text, content_type, crawl_url, dify_segment, dify_subtract, dify_qa_subtract, client=None, business_context=None, quality_profile='')`

## Description

处理单条 HTML 正文，根据长度切分并调用 Dify 抽取 QA。新增可选业务上下文，用于约束抽取方向；不传时旧行为不变。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| formatted_text | str | 是 | HTML 正文 |
| content_type | str | 是 | 内容类型，`qa` 走 QA 专用工作流 |
| crawl_url | str | 是 | 来源 URL |
| dify_segment / dify_subtract / dify_qa_subtract | object | 是 | Dify 请求实例 |
| client | str\|None | 否 | 客户名，作为 other_inputs 传入 |
| business_context | dict\|None | 否 | 业务上下文 |
| quality_profile | str | 否 | 质量画像 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | `parse_answer` 解析出的 QA 列表 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/web/processing/qa_generation.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
