# tests.retrieval.test_business_http_contract.test_openapi_matches_business_contract

## Inputs

The retrieval app and `tests/fixtures/business_retrieval_contract.json`, the current business API contract.

## Outputs

The twelve original OpenAPI paths, request/response models, aliases, defaults and declared validation responses equal the unchanged fixture. The only extra paths are the four ontology paths (eight operations), whose new schemas and responses are covered separately in tests/retrieval/ontology/test_http_contract.py. No startup lifecycle or external I/O executes.

## SQL

None.

## Source

`tests/retrieval/test_business_http_contract.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
