# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_knn_clause

## Signature

`EsSearchInterfaceES8._build_knn_clause(self, query_vector: Sequence[float], vector_field: str='indexes.embedding', k: int=10, num_candidates: Optional[int]=None, filter_query: Optional[Dict[str, Any]]=None, with_inner_hits: bool=False) -> Dict[str, Any]`

## Inputs

query vector、字段、k、num_candidates、可选 ES8 pre-filter、可选 nested inner_hits。

query vector、字段、k、num_candidates、可选 pre-filter。

## Outputs

ES8 native KNN query；nested 字段使用 `nested + score_mode=max`，不生成 `script_score`；过滤条件写入 `knn.filter`。
Nested inner_hits remain at nested query level; request _source includes use fully qualified dynamic nested paths (indexes.text/indexes.embedding or image_indexes.text/image_indexes.embedding), size3/namebest_index retained. Response source remains relative; field filtering is request-only, no persisted mapping/source edits.

ES8 native KNN query；nested 字段使用 nested + score_mode=max，过滤条件写入 knn.filter。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
