# kdb.retrieval.engines.es_maintenance.run_native_update

## Signature

`run_native_update(client: Any, request: Dict[str, Any], *, scroll_size: int=30, request_timeout_seconds: int=3600, max_attempts: int=12, client_api: int=8) -> Dict[str, Any]`

## Inputs

Existing client and prepared native update_by_query keyword arguments; positive scroll_size, timeout, bounded attempts; client transport version supplied by the engine. No new client creation.

## Outputs

Validated synchronous updated/total/version_conflicts/failures result; wait for string task IDs. Shrink size and retry only a confirmed zero-progress write-size rejection. Terminal errors, malformed statistics, exhausted retries and timeouts raise; partial writes are not replayed automatically or represented as success. Unknown transport outcomes are not manually retried.

## SQL / ES

Native `_update_by_query` and read-only `_tasks` polling. Existing query/assignment parameters unchanged. ES8 uses client.options(request_timeout=...). No SQL. Used only in opt-in maintenance mode.

## Source

`src/kdb/retrieval/engines/es_maintenance.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
