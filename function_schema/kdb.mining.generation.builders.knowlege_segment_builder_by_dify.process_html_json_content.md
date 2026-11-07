# kdb.mining.generation.builders.knowlege_segment_builder_by_dify.process_html_json_content

## Signature

`process_html_json_content(html_json_content, process_field_key, dify_segment, dify_index, platform=None, business_context=None, quality_profile='')`

## Description

处理单个 HTML JSON，切分正文并调用 Dify 生成 segment 索引词。新增业务上下文仅用于 Dify 请求约束，最终 segment content 仍保存原始网页片段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| html_json_content | dict | 是 | HTML JSON 内容 |
| process_field_key | str | 是 | 正文字段 |
| dify_segment / dify_index | object | 是 | Dify 请求实例 |
| platform | str\|None | 否 | 平台名 |
| business_context | dict\|None | 否 | 业务上下文 |
| quality_profile | str | 否 | 质量画像 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict]\|None | HTML segment 列表 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/generation/builders/knowlege_segment_builder_by_dify.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
