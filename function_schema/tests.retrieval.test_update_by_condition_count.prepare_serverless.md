# tests.retrieval.test_update_by_condition_count.prepare_serverless

## Signature

`prepare_serverless(client, index, count)`

## Inputs

ES8 假客户端、物理索引和快照文档数。

## Outputs

配置仅外部 ES API 的替身：PIT/search 返回完整 source、版本与精确总数，bulk index 返回逐条 updated；source 已含目标值，允许重复调用验证同值更新。无真实网络或写入。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
