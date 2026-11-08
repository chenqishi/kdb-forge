# kdb.mining.common.quality.audit_generated_qa.build_judge_prompt

## Signature

`build_judge_prompt(doc: Dict[str, Any], annotation: Dict[str, Any], max_history_chars: int=4000) -> str`

## Description

拼一条 QA 的审核 prompt（单条判定，不分块——上下文平均 1.3k 字符、最长 3.6k，
不能像 `relabel_qa_quality_by_llm` 那样 20 条一批塞进去）。

## Inputs

- `doc` (Dict) — 含 `title` / `content` / `chat_history`
- `annotation` (Dict) — `annotate_chat_history` 的产物
- `max_history_chars` (int, 默认 4000) — 上下文截断上限，从**尾部**保留（答案在结尾）

## Outputs

`str` — 用户消息全文。要求模型输出**单个 JSON 对象**：

```json
{"business_related": true, "generic": true, "answer_source": "colleague|customer|official|unknown",
 "verdict": "keep|downgrade", "tags": ["不通用"], "reason": "≤50字"}
```

## SQL

无。

## Source

`src/kdb/mining/common/quality/audit_generated_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
