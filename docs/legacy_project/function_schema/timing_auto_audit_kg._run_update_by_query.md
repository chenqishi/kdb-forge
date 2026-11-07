# _run_update_by_query

> 2026-10-19：审核脚本的同名私有wrapper仅转发query与字段赋值，详见 timing_auto_audit_kg.AutoAuditProcessor._run_update_by_query.md。原批次/异步保护已迁入 `es_maintenance.run_native_update` / `wait_for_update_task`；以下为历史排错记录，不作为当前调用签名。

## 所属文件
`control_script/timing_auto_audit_kg.py`

## 功能描述
执行 `update_by_query` 并兜住阿里云 / AWS ES Serverless 的两个坑：
单请求写入大小超限（减半 `scroll_size` 重试）、以及**运行超 60 秒自动转异步**（轮询 task）。

## Inputs
- `index_name` (str)
- `body` (Dict) — 含 `query` 与 `script`
- `scroll_size` (int) — 起始 scroll 批次大小
- `min_scroll_size` (int, 默认 1)
- `max_attempts` (int, 默认 12)
- `request_timeout_seconds` (int, 默认 3600)

## Outputs
`Dict` — `{updated, failures, scroll_size_used, attempts}`

## 必须兼容的三种返回结构
| 场景 | 结构 |
|---|---|
| 同步完成 | `{updated, failures}` |
| 整批被拒（写入超限） | `{task: {status: {...}}, error: {...}}` |
| **转异步** | `{"task": "<node>:<id>"}` —— `task` 是**字符串** |

第三种是 2026-09-03 踩到的：阿里云 ES Serverless 即使传了 `wait_for_completion=true`，
单次运行超过 60 秒也会自动转异步（客户端会打
`ElasticsearchDeprecationWarning: If the runtime exceeds 60 seconds, this execution
will switch to asynchronous execution`）。原代码 `result.get("task", {}).get("status", result)`
直接 `AttributeError: 'str' object has no attribute 'get'`，
表现为「待审 5289 条、成功 0、失败 1」，一条都没更新。
现在遇到字符串 task 就调 `_wait_for_task_result` 轮询。

wayfair 索引实测：`scroll_size=30` 时一批 24MB > 15MB 上限被拒，减半到 15 后单次运行超 60 秒转异步。
**两个坑会连着出现**，只修一个不够。

## SQL / ES schema
写 ES：按 `body.script` 改 `audit_result`。查询条件用 `from_type_norm` / `audit_result=-1` /
`quality_level` / `insert_time`。索引里没有 `create_time`。

## 测试
`tests/test_auto_audit_update_by_query.py`
