# tests.support.forge_transport.test_duplicate_config_is_rejected

## Signature

`test_duplicate_config_is_rejected(es8_stack)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: synthetic ES8 SDK transport state, pytest monkeypatch/config arguments.
Outputs: deterministic embeddings/provider responses or exact public update/config assertions. Preserve document fields, vector synchronization, index routing and constructor argument validation. No real ES/SQL/LLM I/O.
SQL: none.
Source: tests/support/forge_transport.py

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/support/forge_transport.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
