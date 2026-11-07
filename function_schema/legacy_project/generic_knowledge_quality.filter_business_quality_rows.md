# generic_knowledge_quality.filter_business_quality_rows

## 描述
按业务知识质量画像过滤知识行，拒绝 boilerplate、未通过自包含修复（needs_review）、单薄无具体值的行。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rows | list[dict] | 是 | 知识行（建议先经 repair_self_contained_knowledge_rows） |
| quality_profile | str | 否 | 质量画像，默认 business_task_knowledge |
| title_field | str | 否 | 标题字段名，默认 title（QA 流程传 'q'） |
| content_field | str | 否 | 内容字段名，默认 content（QA 流程传 'a'） |

## Outputs

| 类型 | 说明 |
|------|------|
| (list[dict], list[dict]) | (kept_rows, rejected_rows)；被拒行带 reject_reason |

## 拒绝优先级
1. `boilerplate`：命中版权/隐私/关注公众号/扫码/点赞/在看/阅读原文/免责声明等。
2. `needs_review_dangling_or_generic`：repair 后仍悬空/泛标题。
3. `thin_no_concrete_value`：内容过短且不含数字/URL/步骤/费率等具体值（仅 business_task_knowledge）。

## 备注
- 通用，不硬编码客户。被拒不静默丢弃，保留在 rejected 供审核。
