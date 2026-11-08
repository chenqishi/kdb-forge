# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search_by_vector

## Signature

`search_by_vector(self, query_vector: List[float], vector_field: str, size: int=10, min_score: float=0.0, return_score: bool=False, extra_query: Optional[Dict[str, Any]]=None, index_names: IndexNames=None) -> Any`

## Inputs

query vector、vector field、size/min_score、return_score、extra_query、目标索引。

## Outputs

按 provider 合并的 ES8 native KNN 结果列表；`return_score=True` 时返回 `(doc, score)`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
