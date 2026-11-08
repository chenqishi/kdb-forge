# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_search_query

## Signature

`_build_search_query(self, query: Mapping[str, Any], include_text: bool=True, include_vector: bool=True, vector_k: int=10, with_inner_hits: bool=False) -> Dict[str, Any]`

## Inputs

通用 query dict、BM25/vector 开关、KNN k。

## Outputs

传给 ES8 `search(query=...)` 的 bool DSL。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
