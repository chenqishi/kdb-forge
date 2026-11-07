# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.scroll_search

## Signature

`EsSearchInterfaceES8.scroll_search(self, query: Dict[str, Any], batch_size: int=1000, scroll_timeout: str='5m', index_names: IndexNames=None) -> Iterator[Dict[str, Any]]`

## Inputs

query、batch_size、scroll_timeout、目标索引。

## Outputs

按 provider 依次产生的旧 scroll 检索迭代器。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
