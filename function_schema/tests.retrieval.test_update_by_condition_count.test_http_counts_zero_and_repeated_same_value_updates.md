# tests.retrieval.test_update_by_condition_count.test_http_counts_zero_and_repeated_same_value_updates

## Signature

`test_http_counts_zero_and_repeated_same_value_updates(update_api, provider, index, count)`

## Inputs

PaaS/Serverless 两条路径；0、1、3 条已含目标值的文档。

## Outputs

真实 HTTP→service→ingestion→ES8 链路重复请求均返回 success=true 与精确条数；验证响应字段不变、AND 查询及实际写请求保留。0 不误判失败，不用真实 ES。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
