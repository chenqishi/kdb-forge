# kdb.services.retrieval.app.module

## Description

# Canonical retrieval service startup

## Inputs

Same business argv/environment and current working directory.

## Outputs

Uvicorn worker/reload import target is `kdb.services.retrieval.app:app`; retain host=0.0.0.0, port=8003, reload=False, workers=int(SEARCH_SERVICE_WORKERS or default 4), existing initial constructor/load timing and all routes/protocol values. 

## SQL

No SQL/ES/HTTP query change. Validation substitutes server/client boundaries and runs no real service or worker.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
