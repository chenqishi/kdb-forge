# tests.retrieval.test_update_by_condition_count.test_native_count_uses_updated_not_total

## Signature

`test_native_count_uses_updated_not_total(update_api, updated)`

## Inputs

原生 ES8 返回 updated=0/2、total=5、余下为 noops 的响应。

## Outputs

引擎严格返回整数 updated，不能以 total 回填或 bool 转换；不额外发 count。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
