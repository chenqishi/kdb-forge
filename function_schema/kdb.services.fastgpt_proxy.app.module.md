# kdb.services.fastgpt_proxy.app.module

## Description

# Canonical fastgpt_proxy service startup

## Inputs

Same business argv/environment and current working directory.

## Outputs

Uvicorn worker/reload import target is `kdb.services.fastgpt_proxy.app:app`; retain host=0.0.0.0, port=8000, reload=True, existing initial constructor/load timing and all routes/protocol values. 

## SQL

No SQL/ES/HTTP query change. Validation substitutes server/client boundaries and runs no real service or worker.

## Source

`src/kdb/services/fastgpt_proxy/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
