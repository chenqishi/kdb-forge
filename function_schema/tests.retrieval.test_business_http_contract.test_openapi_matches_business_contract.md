# tests.retrieval.test_business_http_contract.test_openapi_matches_business_contract

## Inputs

The retrieval app and `tests/fixtures/business_retrieval_contract.json`, the current business API contract.

## Outputs

The complete OpenAPI paths, request/response models, aliases, defaults and declared validation responses equal the contract. No startup lifecycle or external I/O executes.

## SQL

None.

## Source

`tests/retrieval/test_business_http_contract.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
