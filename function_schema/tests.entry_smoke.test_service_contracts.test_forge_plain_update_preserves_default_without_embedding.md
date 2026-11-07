# tests.entry_smoke.test_service_contracts.test_forge_plain_update_preserves_default_without_embedding

## Signature

`test_forge_plain_update_preserves_default_without_embedding()`

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

`tests/entry_smoke/test_service_contracts.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
