# tests.retrieval.test_update_by_condition_count.test_native_failures_raise_and_http_reports_failure

## Signature

`test_native_failures_raise_and_http_reports_failure(update_api, failure)`

## Inputs

原生 ES8 版本冲突、失败条目、超时、缺失/非法计数、未完成任务和传输异常。

## Outputs

引擎抛 RuntimeError；HTTP success=false、updated_count=0，消息说明可能已有部分写入且不自动回滚。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
