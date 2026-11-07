# knowledge_html_clear_by_dify.build_html_context_prefix

## 描述
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
