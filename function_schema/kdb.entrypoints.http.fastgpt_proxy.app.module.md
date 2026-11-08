# kdb.entrypoints.http.fastgpt_proxy.app.module

## Description

# Canonical fastgpt_proxy service startup

## Inputs

Same business argv/environment and current working directory.

## Outputs

Uvicorn worker/reload import target is `kdb.entrypoints.http.fastgpt_proxy.app:app`; retain host=0.0.0.0, port=8000, reload=True, existing initial constructor/load timing and all routes/protocol values.

## SQL

No SQL/ES/HTTP query change. Validation substitutes server/client boundaries and runs no real service or worker.

## Source

`src/kdb/entrypoints/http/fastgpt_proxy/app.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
