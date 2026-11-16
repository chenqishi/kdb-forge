# tests.retrieval.test_update_by_condition_count.test_http_sums_updates_across_provider_groups

## Signature

`test_http_sums_updates_across_provider_groups(update_api)`

## Inputs

PaaS、Serverless、PaaS 交错索引组，更新数分别 2、3、4。

## Outputs

HTTP 返回精确合计 9，包含同 provider 的多个组；每组只使用自己的索引和客户端。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
