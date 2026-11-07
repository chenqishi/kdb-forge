# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_search_query

## Signature

`EsSearchInterfaceES8._build_search_query(self, query: Mapping[str, Any], include_text: bool=True, include_vector: bool=True, vector_k: int=10, with_inner_hits: bool=False) -> Dict[str, Any]`

## Inputs

通用 query dict、BM25/vector 开关、KNN k。

## Outputs

传给 ES8 `search(query=...)` 的 bool DSL。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
