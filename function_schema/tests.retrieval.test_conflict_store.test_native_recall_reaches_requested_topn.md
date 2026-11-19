# tests.retrieval.test_conflict_store.test_native_recall_reaches_requested_topn

## Signature

`test_native_recall_reaches_requested_topn(routed_clients, size, expected_k)`

## Inputs

参数以签名为准。

## Outputs

离线行为验证/明确的测试夹具，不访问生产数据。

## SQL / ES

无SQL；测试仅替换外部边界。真实LLM服务验证仅由独立入口显式启动。

## Source

`tests/retrieval/test_conflict_store.py`
