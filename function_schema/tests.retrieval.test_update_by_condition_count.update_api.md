# tests.retrieval.test_update_by_condition_count.update_api

## Signature

`update_api(routed_clients, monkeypatch)`

## Inputs

ES8 路由 fixture 和 pytest monkeypatch。

## Outputs

返回真实 HTTP TestClient、ES8 引擎与假客户端；SearchDataInterface 使用真实 update_data_value，替换 runtime 实例。禁止额外 count 调用，测试结束恢复补丁。

## SQL

无；仅替换外部 ES API，在离线守卫下执行。

## Source

`tests/retrieval/test_update_by_condition_count.py`。
