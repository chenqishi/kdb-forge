# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._validate_query_vectors

## Signature

`_validate_query_vectors(self, query: Mapping[str, Any]) -> None`

## Inputs

旧检索 query，可能含一个或多个向量。

## Outputs

维度正确时无返回；错误时抛 ValueError，即使分页选择 BM25-only。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
