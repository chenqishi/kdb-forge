# wait_for_update_task

## Inputs
Existing client, nonempty task ID, poll interval and timeout.
## Outputs
Completed task envelope, retaining top-level errors and response/status counters for checked handling. Monotonic timeout raises rather than declaring completion. Polling errors propagate; no second mutation request. No cancellation/deletion of task records.
## ES / SQL
Read `_tasks/<id>`; no SQL.

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `client: Any, task_id: str, poll_interval: float=5.0, timeout_seconds: float=3600`.

Behavior / Outputs: Wait for the actual terminal response, preserving task-level errors.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
