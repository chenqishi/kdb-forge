# scripts.testing.offline_guard._inside

## Signature

`_inside(path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: file path or fd. Outputs: whether resolved write target is inside candidate/temp/explicit evidence roots, or devnull. Symlink resolution checked. No SQL/network.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`scripts/testing/offline_guard.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
