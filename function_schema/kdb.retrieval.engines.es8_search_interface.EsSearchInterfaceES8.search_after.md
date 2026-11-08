# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.search_after

## Signature

`search_after(self, query: Dict[str, Any], batch_size: int=1000, sort_field: str='_id', index_names: IndexNames=None) -> Iterator[Dict[str, Any]]`

## Inputs

query、batch_size、sort_field、目标索引。

## Outputs

按 provider 依次产生的旧 search_after 检索迭代器。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
