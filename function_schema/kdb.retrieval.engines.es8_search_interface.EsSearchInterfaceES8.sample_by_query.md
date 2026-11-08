# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.sample_by_query

## Signature

`sample_by_query(self, index_name: str, query: Dict[str, Any], size: int=10, includes: Optional[List[str]]=None) -> List[Dict[str, Any]]`

## Inputs

索引、query DSL、样本数量和 source includes。

## Outputs

返回带 `_id` 的 source 样本文档列表。

## SQL

无；读取 Elasticsearch。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
