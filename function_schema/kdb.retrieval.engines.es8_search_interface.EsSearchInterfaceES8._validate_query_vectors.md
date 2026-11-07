# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._validate_query_vectors

## Signature

`EsSearchInterfaceES8._validate_query_vectors(self, query: Mapping[str, Any]) -> None`

## Inputs

旧检索 query，可能含一个或多个向量。

## Outputs

维度正确时无返回；错误时抛 ValueError，即使分页选择 BM25-only。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
