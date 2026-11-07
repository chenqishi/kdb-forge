# retire

## 所属文件
`data_control_tools/retire_superseded_knowledge.py`

## 功能描述
主流程：读快照 → 取现状 → `plan_retire` 分类 → 落 `rollback.jsonl` → `del_flag=1` + `flag=<批次>`。
**默认 dry-run**，要写回必须显式 `--execute`。

## Inputs
- `config_path` (str, 默认 `config/config_es_engine.json`)
- `index` (str)
- `snapshot_file` (str)
- `flag_value` (str) — 批次标记，形如 `qa_regen_wayfair_20260903`
- `work_dir` (str) — `rollback.jsonl` 落盘目录
- `new_since` (Optional[str])
- `bulk_batch` (int, 默认 `DEFAULT_BULK_BATCH`=200)
- `execute` (bool, 默认 False)

## Outputs
`Dict` — `{planned, rollback_file, skipped:{...}, [dry_run], [updated], [failed]}`

## SQL / ES schema
写 ES（`_bulk` partial update）：
- `del_flag` ← `1`
- `flag` ← `flag_value`

其余字段一概不动。写回前**先**把每条的旧 `del_flag`/`flag` 落 `rollback.jsonl`（dry-run 也会落，
方便先看名单）。批次标记的既定字段是 `flag`，**不是 `del_reason`**——
`del_reason` 只在 `insert_data` 覆盖重复数据时写 `cover_by_new`。

## 复核
写回后立刻查会读到矛盾数字（refresh 延迟），必须隔一轮再对账，见 memory `es-batch-write-verify-lag`。
