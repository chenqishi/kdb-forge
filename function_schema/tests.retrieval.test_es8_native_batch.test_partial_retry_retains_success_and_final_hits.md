# tests.retrieval.test_es8_native_batch.test_partial_retry_retains_success_and_final_hits

## Signature

`test_partial_retry_retains_success_and_final_hits(routed_clients, monkeypatch, caplog, retry_transport_failure)`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## Source

`tests/retrieval/test_es8_native_batch.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
