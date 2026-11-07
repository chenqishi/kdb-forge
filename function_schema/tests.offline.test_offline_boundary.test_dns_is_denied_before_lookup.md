# tests.offline.test_offline_boundary.test_dns_is_denied_before_lookup

## Signature

`test_dns_is_denied_before_lookup()`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Actual getaddrinfo must fail before DNS resolution. No external IO/SQL.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/offline/test_offline_boundary.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
