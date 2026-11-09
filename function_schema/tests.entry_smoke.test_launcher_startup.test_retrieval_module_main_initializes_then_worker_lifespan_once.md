# tests.entry_smoke.test_launcher_startup.test_retrieval_module_main_initializes_then_worker_lifespan_once

## Signature

`test_retrieval_module_main_initializes_then_worker_lifespan_once(monkeypatch, tmp_path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Run the retrieval CLI with recording factories and a modeled worker lifespan. Assert retained initialization counts, route/host/port/workers, repeated lifespan idempotence and restoration of the previously imported canonical app module. The entry module is isolated; shared runtime state and patches stay intact.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_launcher_startup.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
