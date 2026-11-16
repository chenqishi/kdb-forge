# tests.retrieval.test_update_by_condition_count.test_empty_patch_is_zero_without_backend_calls

## Signature

`test_empty_patch_is_zero_without_backend_calls(update_api)`

## Inputs

直接调用引擎并传空更新字段。

## Outputs

返回严格整数 0，不执行 ES 查询或写入；保留 HTTP 空字段校验。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
