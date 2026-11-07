# wayfair_unanswered_review.judge_coverage

## 描述
用 DeepSeek 官方强模型判断「检索到的知识能否回答这条 query」，输出三档结论。
不用纯相似度阈值，因为 `MEMORY.md` 已记录该库上纯向量阈值区分度不足
（真重复 0.883 / 假重复 0.963，区间重叠），且阈值无法识别「检索到了但答非所问」。

三档：
- `covered`：库里有知识能直接回答 → 说明是检索/召回或线上 rerank 问题，不是知识缺失
- `partial`：沾边但不足以完整回答 → 知识需补充细节
- `missing`：确实没有相关知识 → 真知识缺口，需补录

同时输出 `evidence_ids`（支撑判断的知识 `_id`）与 `reason`、`suggested_knowledge`（missing/partial 时建议补什么）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | str | 是 | 原始用户 query |
| normalized_query | str | 是 | 补全后的 query |
| candidates | list[dict] | 是 | `search_knowledge` 的返回 |
| model | str | 否 | 默认 `deepseek-v4-pro` |
| max_retries | int | 否 | 坏 JSON 重试次数，默认 3 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | `{"verdict": "covered\|partial\|missing", "reason": str, "evidence_ids": list[str], "suggested_knowledge": str}`；模型不可用时 `verdict="unknown"` |

## SQL

无。
