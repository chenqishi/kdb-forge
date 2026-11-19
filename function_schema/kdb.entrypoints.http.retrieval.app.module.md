# kdb.entrypoints.http.retrieval.app.module

## Description

# Canonical retrieval service startup

## Inputs

Same business argv/environment and current working directory.

## Outputs

Uvicorn worker/reload import target is `kdb.entrypoints.http.retrieval.app:app`; retain host=0.0.0.0, port=8003, reload=False, workers=int(SEARCH_SERVICE_WORKERS or default 4), existing initial constructor/load timing and all routes/protocol values.

## SQL

No SQL/ES/HTTP query change. Validation substitutes server/client boundaries and runs no real service or worker.

## Source

`src/kdb/entrypoints/http/retrieval/app.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。

## Optional knowledge tools

`register_dedup_routes` reads an explicitly provided KDB_DEDUP_HARNESS_CONFIG. Absent/disabled configuration adds no route. When enabled, POST /knowledge_dedup/mcp requires a server-bound admin leader credential and index authorization; existing routes/auth/defaults are unchanged.
