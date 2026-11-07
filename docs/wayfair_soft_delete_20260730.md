# Wayfair Knowledge Soft Delete 2026-07-30

## Scope

Client/index: `wayfair`

Requested filename keywords:

- `订单导出`
- `托盘化`
- `产品定价_如何在定价主页创建促销活动 (Archived)`
- `CastleGate_ CastleGate 支持服务 (Archived)`
- `商用级别标准概览`

## Tables And Fields

- `rufitai.dops_task_kggen_info` is the backend execution table used by the task controller, but it has no `del_flag` column in the current MySQL schema.
- The file-level frontend knowledge-mining task table is `rufitai.rf_knowledge_mining_task`; it has `file_name`, `client`, `task_id`, and `del_flag`.
- ES soft delete uses `del_flag=1`; this run also writes `flag="20260730"` for documents updated from active state.

## Executed Updates

Auto-deleted only one-to-one or normalized one-to-one file matches:

- `订单导出.docx`
- `CastleGate_ CastleGate 支持服务.docx`
- `商用级别标准概览.docx`

MySQL:

- Updated `rufitai.rf_knowledge_mining_task` where `client='wayfair'`, exact `file_name` in the auto-deleted set, and `IFNULL(del_flag, 0) != 1`.
- Updated rows: `3`.

ES:

- Updated index `wayfair` with exact `ext_info.from_file_name.keyword` terms.
- Query required active knowledge: `del_flag=0`.
- Update set `del_flag=1` and `flag="20260730"`.
- Updated active docs: `82`.

## Verification

Corrected ES post-verification for the auto-deleted files:

- Total docs across all del flags: `86`
- Remaining `del_flag=0`: `0`
- `del_flag=1` total: `86`
- `del_flag=1` and `flag=20260730`: `82`

The difference of `4` docs were already `del_flag=1` before this run, so they were not touched by the active-doc update query and do not carry the `20260730` flag.

Report artifacts:

- `output/wayfair_soft_delete_20260730/wayfair_soft_delete_report.json`
- `output/wayfair_soft_delete_20260730/mysql_candidate_rows.csv`

## Needs Manual Selection

`托盘化` matched multiple active ES source files and was not deleted:

- `托盘化指南.docx`: `32`
- `托盘化.docx`: `10`

Follow-up user confirmation: both `托盘化指南.docx` and `托盘化.docx` should be deleted.

Executed follow-up updates:

- MySQL `rufitai.rf_knowledge_mining_task`: updated `2` rows to `del_flag=1`.
- ES `wayfair`: updated `42` active docs to `del_flag=1, flag="20260730"`.
- Post-verification remaining active docs for these two files: `0`.
- Report artifact: `output/wayfair_soft_delete_20260730/wayfair_palletization_delete_report.json`.

`产品定价_如何在定价主页创建促销活动 (Archived)` had no exact or normalized one-to-one match. Nearby active candidates observed:

- `产品定价_关于促销活动.docx`: `9`
- `商品级促销活动.docx`: `36`
- `欧洲站主要促销活动说明.docx`: `8`
- `定价主页（Pricing Home) 中的 B2B 日常折扣.docx`: `22`
- `定价主页 (Pricing Home) 概览.docx`: `16`
- `定价主页（Pricing Home）中的 CastleGate 降价.docx`: `12`

Follow-up note: user explicitly asked to leave `产品定价_关于促销活动.docx` untouched for now. Verification after the palletization delete showed its active ES count remained `9` and MySQL `del_flag` remained `0`.

## 2026-08-01 Follow-Up

Requested:

- `订单导出`
- `Wayfair 大件包裹 (LP) 发货准备自查清单`

Results:

- `订单导出` resolved to `订单导出.docx`; it was already cleared from the 2026-07-30 run. MySQL `del_flag=1`; ES active count remained `0`.
- `Wayfair 大件包裹 (LP) 发货准备自查清单` did not exist as a literal MySQL/ES source filename. ES title/content search resolved it to source file `WGS one page check list.docx`, with QA title sample `大件包裹(LP) 发货准备的核心目标是什么？`.

Executed updates for `WGS one page check list.docx`:

- MySQL `rufitai.rf_knowledge_mining_task`: updated `1` row to `del_flag=1`.
- ES `wayfair`: updated `34` active docs to `del_flag=1, flag="20260730"`.
- Corrected post-verification:
  - total docs all del flags: `34`
  - remaining `del_flag=0`: `0`
  - `del_flag=1`: `34`
  - `del_flag=1 AND flag=20260730`: `34`
- Report artifact: `output/wayfair_soft_delete_20260730/wayfair_lp_checklist_delete_report.json`.

Reusable skill created:

- `~/.codex/skills/wayfair-knowledge-soft-delete`
- Use it for future Wayfair document/knowledge soft-delete requests.
