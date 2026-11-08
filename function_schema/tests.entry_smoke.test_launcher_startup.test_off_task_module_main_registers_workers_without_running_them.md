# tests.entry_smoke.test_launcher_startup.test_off_task_module_main_registers_workers_without_running_them

## Signature

`test_off_task_module_main_registers_workers_without_running_them(monkeypatch, tmp_path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: synthetic pytest config/model/auth and patched ES/SQL/serve/thread boundaries.
Outputs: kdb.entrypoints.cli.generate_segments canonical service modules with unchanged business argv, cwd, route set, host/port/workers and initialization counts. Preflight execs the selected interpreter with -m and the canonical module name. No socket, subprocess or real SQL/model/LLM execution.
SQL: pool construction is replaced with a recording fixture.
Source: tests/entry_smoke/test_launcher_startup.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_launcher_startup.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
