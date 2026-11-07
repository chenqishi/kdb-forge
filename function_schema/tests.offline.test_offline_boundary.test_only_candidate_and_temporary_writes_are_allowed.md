# tests.offline.test_offline_boundary.test_only_candidate_and_temporary_writes_are_allowed

## Signature

`test_only_candidate_and_temporary_writes_are_allowed(tmp_path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs tmp_path. Temporary fixture write allowed, outside target /dev/full open denied before access. No old workspace write/SQL.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/offline/test_offline_boundary.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
