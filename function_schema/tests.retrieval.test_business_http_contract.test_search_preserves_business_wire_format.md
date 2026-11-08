# tests.retrieval.test_business_http_contract.test_search_preserves_business_wire_format

## Inputs

An HTTP POST to `/search` with a synthetic `test_index` request and a replaced async search boundary returning one synthetic document.

## Outputs

The business request succeeds without a new authentication requirement; default `top_k=100` and existing query parameters reach the boundary unchanged. Response status and JSON fields match the business API contract. The test does not enter lifespan, query ES or generate knowledge.

## SQL

None.

## Source

`tests/retrieval/test_business_http_contract.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
