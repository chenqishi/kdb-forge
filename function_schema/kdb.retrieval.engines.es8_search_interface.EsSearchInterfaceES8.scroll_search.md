# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.scroll_search

## Signature

`scroll_search(self, query: Dict[str, Any], batch_size: int=1000, scroll_timeout: str='5m', index_names: IndexNames=None) -> Iterator[Dict[str, Any]]`

## Inputs

query、batch_size、scroll_timeout、目标索引。

## Outputs

按 provider 依次产生的旧 scroll 检索迭代器。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
