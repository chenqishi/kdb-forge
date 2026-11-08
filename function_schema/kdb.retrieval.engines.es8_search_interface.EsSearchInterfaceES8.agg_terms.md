# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.agg_terms

## Signature

`agg_terms(self, index_name: str, query: Dict[str, Any], field: str, size: int=1000, sub_aggs: Optional[Dict[str, Any]]=None) -> List[Dict[str, Any]]`

## Inputs

index、query DSL、terms 字段、聚合 size、可选子聚合。

## Outputs

通过 ES8 `search(query=..., aggs=...)` 返回 buckets 列表。

## SQL

无；底层读取 Elasticsearch。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
