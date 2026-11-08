# tests.retrieval.test_es8_interface.test_dual_budget_and_cross_provider_index_are_preserved

## Signature

`test_dual_budget_and_cross_provider_index_are_preserved(routed_clients)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

Exercise real ES8 engine + Router using native msearch boundary. Each provider gets two independent bodies size5; route query/inner_hits and returned provider order unchanged.

## SQL

None.

## Source

`tests/retrieval/test_es8_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
