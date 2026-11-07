# kdb.integrations.data_control.audit_chat_auto_qa_by_llm.judge_all

## Signature

`judge_all(docs: List[Dict[str, Any]], colleague_names: Sequence[str], decision_file: str, model: str='', concurrency: int=4) -> List[Dict[str, Any]]`

## Description

并发跑 LLM 判定，逐条落盘 `decisions.jsonl`，可断点续跑。

## Inputs

- `docs` / `colleague_names` / `model` / `concurrency` (默认 4) / `decision_file`

## Outputs

`List[Dict]`，每条含 `_id` / `title` / `content` / `old_level` / `new_level` /
`verdict` / `tags` / `reason` / `answer_source` / `answer_speaker` / `skip_reason`。

## 不能错的语义（与 relabel_qa_quality_by_llm 保持一致）

1. **判不出来就不动**：LLM 返回空、JSON 解不出、字段缺失 → `new_level = old_level`
   并记 `skip_reason`，绝不默认降级。
2. **降级档位**：`answer_source == 'customer'` 或 `business_related=false` 或
   `generic=false` → `low`；模型自己说不确定（`verdict=downgrade` 但三个维度都过）→ `mid`。
3. 已在 `decisions.jsonl` 里的 `_id` 直接跳过（续跑不重复烧 token）。

## SQL

无。

## Source

`src/kdb/integrations/data_control/audit_chat_auto_qa_by_llm.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
