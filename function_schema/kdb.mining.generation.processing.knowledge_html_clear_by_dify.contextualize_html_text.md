# kdb.mining.generation.processing.knowledge_html_clear_by_dify.contextualize_html_text

## Signature

`contextualize_html_text(formatted_text, business_context=None, quality_profile='')`

## Description

为 HTML 正文附加业务抽取约束。无业务上下文时原样返回正文。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| formatted_text | str | 是 | HTML 正文文本或分片 |
| business_context | dict\|None | 否 | 业务上下文 |
| quality_profile | str | 否 | 质量画像 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 发给 Dify 的文本 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/generation/processing/knowledge_html_clear_by_dify.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
