# tests.entry_smoke.test_launcher_startup.run_service

## Signature

`run_service(monkeypatch, tmp_path, module, args)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: synthetic pytest config/model/auth and patched ES/SQL/serve/thread boundaries.
Outputs: executes the requested service as __main__ with unchanged argv and patched external boundaries. Temporarily removes only that entry module from sys.modules and its parent package attribute; restores both original bindings in finally, including after failure. Shared business/runtime modules remain loaded so their patched state and identity are preserved. No warning suppression, socket, subprocess or real SQL/model/LLM execution.
SQL: pool construction is replaced with a recording fixture.
Source: tests/entry_smoke/test_launcher_startup.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_launcher_startup.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
