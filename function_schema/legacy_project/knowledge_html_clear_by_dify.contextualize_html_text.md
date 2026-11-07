# knowledge_html_clear_by_dify.contextualize_html_text

## 描述
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
