# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.get_unique_values

## Signature

`EsSearchInterfaceES8.get_unique_values(self, index_name: str, field_name: str, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None) -> Union[List[str], List[Dict[str, Any]]]`

## Inputs

索引、字段、聚合 size、是否返回计数、额外过滤。

## Outputs

通过 ES8 `search(query=..., aggs=...)` 返回唯一值列表或带 doc_count 的对象列表。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
