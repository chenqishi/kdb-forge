# tests.retrieval.test_business_http_contract.test_request_models_match_business_contract

## Inputs

Parameterized synthetic request data and the expected validation result for each business request model.

## Outputs

Valid requests preserve their serialized fields, aliases and default values. Invalid requests retain their error types and field locations, including explicit null, physical-index restrictions, local time format and preview size limits. No backend is constructed.

## SQL

None.

## Source

`tests/retrieval/test_business_http_contract.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
