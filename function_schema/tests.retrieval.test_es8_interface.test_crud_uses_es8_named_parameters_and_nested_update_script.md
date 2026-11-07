# tests.retrieval.test_es8_interface.test_crud_uses_es8_named_parameters_and_nested_update_script

## Signature

`test_crud_uses_es8_named_parameters_and_nested_update_script(routed_clients)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: original routed fake clients. Outputs: Serverless insert/partial update retains ES8 named doc API; PaaS conditional update retains native nested Painless assignment. Serverless conditional update is independently covered by actual business/service + PIT/CAS tests. Do not demand banned script serialization on Serverless just to preserve an obsolete transport assertion; public request semantics remain unchanged. Only mocked client boundary, no live calls.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/retrieval/test_es8_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
