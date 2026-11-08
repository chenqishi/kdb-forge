# tests.services.test_extracted_business_adapters.test_fastgpt_transport_and_http_error_contract

## Signature

`test_fastgpt_transport_and_http_error_contract(monkeypatch, status)`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

精确校验上游 URL、请求头、JSON 与响应；保留成功 JSON 和 503 HTTPException。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/services/test_extracted_business_adapters.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
