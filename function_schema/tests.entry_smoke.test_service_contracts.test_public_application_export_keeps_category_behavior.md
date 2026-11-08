# tests.entry_smoke.test_service_contracts.test_public_application_export_keeps_category_behavior

## Signature

`test_public_application_export_keeps_category_behavior()`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: synthetic request/config and monkeypatched service factories.
Outputs: exact twelve POST routes; current public SearchDataInterface retains category methods; lifespan creates one interface/modifier pair; update retains payload fields and no unnecessary embedding. No external I/O.
SQL: none.
Source: tests/entry_smoke/test_service_contracts.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/entry_smoke/test_service_contracts.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
