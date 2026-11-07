# kdb.integrations.data_control.audit_chat_auto_qa_by_llm.build_target_query

## Signature

`build_target_query(from_type: str='chat_auto', data_type: str='qa', quality_level: str='high', audit_results: Sequence[int]=(-1,), random_seed: int=0) -> Dict[str, Any]`

## Description

圈定「自动学习产出、当前 high、尚未人工审核」的 QA。

## Inputs

- `from_type` (str, 默认 `chat_auto`)
- `data_type` (str, 默认 `qa`)
- `quality_level` (str, 默认 `high`)
- `audit_results` (List[int], 默认 `[-1]`) — 只审未审核过的
- `random_seed` (int, 可选) — 传了就包一层 `function_score.random_score` 做随机抽样

## Outputs

`Dict` — ES query。

## 为什么按 `from_type` 而不是 `from_type_norm`

用户口头说的是「from_type_norm 为 chat_auto」，但线上 **`from_type_norm` 里根本没有 `chat_auto`**：
自动学习那批的 `from_type_norm` 是 `auto_learning`(8060) 和历史遗留的中文 `自动学习`(1127)，
`chat_auto` 是 **`from_type`** 的值（9187 条）。
按 `from_type_norm='chat_auto'` 过滤会一条都查不到，按 `auto_learning` 过滤会漏掉 1127 条中文的。
**统一按 `from_type='chat_auto'`**（`docs/payoneer_olive_quality_relabel.md` 里踩过同一个坑）。

## SQL

无。

## Source

`src/kdb/integrations/data_control/audit_chat_auto_qa_by_llm.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
