# tests.offline.test_offline_boundary.test_connect_is_denied_before_network

## Signature

`test_connect_is_denied_before_network()`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Actual stdlib connect must raise boundary error before packet, socket closed. No successful external IO.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/offline/test_offline_boundary.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
