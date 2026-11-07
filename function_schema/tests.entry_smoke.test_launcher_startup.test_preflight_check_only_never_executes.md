# tests.entry_smoke.test_launcher_startup.test_preflight_check_only_never_executes

## Signature

`test_preflight_check_only_never_executes(monkeypatch, capsys)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: synthetic pytest config/model/auth and patched ES/SQL/serve/thread boundaries.
Outputs: kdb.mining.generation.run canonical service modules with unchanged business argv, cwd, route set, host/port/workers and initialization counts. Preflight execs the selected interpreter with -m and the canonical module name. No socket, subprocess or real SQL/model/LLM execution.
SQL: pool construction is replaced with a recording fixture.
Source: tests/entry_smoke/test_launcher_startup.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_launcher_startup.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
