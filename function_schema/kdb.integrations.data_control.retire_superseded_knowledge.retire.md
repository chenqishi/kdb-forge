# kdb.integrations.data_control.retire_superseded_knowledge.retire

## Signature

`retire(config_path: str, index: str, snapshot_file: str, flag_value: str, work_dir: str, new_since: Optional[str]=None, bulk_batch: int=DEFAULT_BULK_BATCH, execute: bool=False) -> Dict[str, Any]`

## Description

主流程：读快照 → 取现状 → `plan_retire` 分类 → 落 `rollback.jsonl` → `del_flag=1` + `flag=<批次>`。
**默认 dry-kdb.mining.generation.run**，要写回必须显式 `--execute`。

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

其余字段一概不动。写回前**先**把每条的旧 `del_flag`/`flag` 落 `rollback.jsonl`（dry-kdb.mining.generation.run 也会落，
方便先看名单）。批次标记的既定字段是 `flag`，**不是 `del_reason`**——
`del_reason` 只在 `insert_data` 覆盖重复数据时写 `cover_by_new`。

## 复核

写回后立刻查会读到矛盾数字（refresh 延迟），必须隔一轮再对账，见 memory `es-batch-write-verify-lag`。

## Source

`src/kdb/integrations/data_control/retire_superseded_knowledge.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
