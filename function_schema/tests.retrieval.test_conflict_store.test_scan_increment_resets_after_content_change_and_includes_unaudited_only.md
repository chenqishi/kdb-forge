# tests.retrieval.test_conflict_store.test_scan_increment_resets_after_content_change_and_includes_unaudited_only

## Signature

`test_scan_increment_resets_after_content_change_and_includes_unaudited_only()`

## Inputs

参数以签名为准。

## Outputs

离线行为验证/明确的测试夹具，不访问生产数据。

## SQL / ES

无SQL；测试仅替换外部边界。真实LLM服务验证仅由独立入口显式启动。

## Source

`tests/retrieval/test_conflict_store.py`
