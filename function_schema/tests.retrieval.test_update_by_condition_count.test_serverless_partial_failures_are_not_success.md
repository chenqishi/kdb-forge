# tests.retrieval.test_update_by_condition_count.test_serverless_partial_failures_are_not_success

## Signature

`test_serverless_partial_failures_are_not_success(update_api, failure)`

## Inputs

先成功一个 PaaS 组，再让 Serverless 出现混合成功与冲突/失败、bulk 数量不完整、传输错误、快照提前结束或超时。

## Outputs

HTTP 不把部分计数或 False 误判为成功；返回失败且说明部分写入；PIT 被关闭。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
