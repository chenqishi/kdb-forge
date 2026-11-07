# kdb.mining.generation.processing.knowledge_html_clear_by_dify.build_html_context_prefix

## Signature

`build_html_context_prefix(business_context, quality_profile='')`

## Description

把业务上下文渲染为给 Dify 的 HTML 抽取约束前缀。前缀明确标记为“禁止作为知识内容输出”。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| business_context | dict\|None | 否 | 业务上下文 |
| quality_profile | str | 否 | 质量画像 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 抽取约束前缀；无上下文时为空 |

## SQL

不读写 SQL。

## Source

`src/kdb/mining/generation/processing/knowledge_html_clear_by_dify.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
