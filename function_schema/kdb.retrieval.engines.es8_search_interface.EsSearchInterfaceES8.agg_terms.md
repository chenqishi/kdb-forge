# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.agg_terms

## Signature

`EsSearchInterfaceES8.agg_terms(self, index_name: str, query: Dict[str, Any], field: str, size: int=1000, sub_aggs: Optional[Dict[str, Any]]=None) -> List[Dict[str, Any]]`

## Inputs

index、query DSL、terms 字段、聚合 size、可选子聚合。

## Outputs

通过 ES8 `search(query=..., aggs=...)` 返回 buckets 列表。

## SQL

无；底层读取 Elasticsearch。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
