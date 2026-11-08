# kdb.retrieval.engines.es_maintenance.wait_for_update_task

## Signature

`wait_for_update_task(client: Any, task_id: str, poll_interval: float=5.0, timeout_seconds: float=3600) -> Dict[str, Any]`

## Inputs

Existing client, nonempty task ID, poll interval and timeout.

## Outputs

Completed task envelope, retaining top-level errors and response/status counters for checked handling. Monotonic timeout raises rather than declaring completion. Polling errors propagate; no second mutation request. No cancellation/deletion of task records.

## SQL / ES

Read `_tasks/<id>`; no SQL.

## Source

`src/kdb/retrieval/engines/es_maintenance.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
