# _wait_for_task_result

> 2026-10-19：审核脚本的私有task轮询已移入统一引擎，不再直接调用客户端。原批次/异步保护已迁入 `es_maintenance.run_native_update` / `wait_for_update_task`；以下为历史排错记录，不作为当前调用签名。

## 所属文件
`control_script/timing_auto_audit_kg.py`

## 功能描述
轮询 ES `_tasks/<task_id>`，等 `update_by_query` 的异步任务跑完。

## Inputs
- `task_id` (str) — 形如 `"<node>:<id>"`
- `poll_interval` (float, 默认 5.0)
- `timeout_seconds` (int, 默认 3600)

## Outputs
`Dict`：
- 任务完成且**没有 error** → 返回 `result["response"]`（扁平的 `{updated, failures, ...}`）
- 任务完成但**带 error**（典型是写入大小超限）→ 返回**整个** task 结果，
  这样调用方 `_run_update_by_query` 才看得到 error 并减半重试。
  只返回 `response` 会把 error 丢掉，退化成「静默 0 条更新」。

超时抛 `TimeoutError`。

## SQL
无。
