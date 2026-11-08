# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search

## Signature

`search(self, query: Optional[Dict[str, Any]]=None, size: int=10, index_names: IndexNames=None) -> List[Dict[str, Any]]`

## Inputs

query、size、目标索引。

## Outputs

旧单路检索结果列表。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
