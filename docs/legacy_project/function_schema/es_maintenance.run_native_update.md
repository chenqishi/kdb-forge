# run_native_update

## Inputs
Existing client and prepared native update_by_query keyword arguments; positive scroll_size, timeout, bounded attempts; client transport version supplied by the engine. No new client creation.
## Outputs
Validated synchronous updated/total/version_conflicts/failures result; wait for string task IDs. Shrink size and retry only a confirmed zero-progress write-size rejection. Terminal errors, malformed statistics, exhausted retries and timeouts raise; partial writes are not replayed automatically or represented as success. Unknown transport outcomes are not manually retried.
## ES / SQL
Native `_update_by_query` and read-only `_tasks` polling. Existing query/assignment parameters unchanged. ES8 uses client.options(request_timeout=...). No SQL. Used only in opt-in maintenance mode.

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `client: Any, request: Dict[str, Any], *, scroll_size: int=30, request_timeout_seconds: int=3600, max_attempts: int=12, client_api: int=8`.

Behavior / Outputs: Run a checked, bounded native update; don't replay an uncertain write.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
