# test_openapi_matches_business_contract

## Inputs

The retrieval app and `tests/fixtures/business_retrieval_contract.json`, the current business API contract.

## Outputs

The complete OpenAPI paths, request/response models, aliases, defaults and declared validation responses equal the contract. No startup lifecycle or external I/O executes.

## SQL

None.

## Source

`tests/retrieval/test_business_http_contract.py`.
