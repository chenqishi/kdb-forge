# kdb.retrieval.search.queries.search_data

## Signature

`search_data(self, query: Dict[str, Any], size: Optional[int]=None, index_names: Optional[Union[str, List[str]]]=None) -> List[Dict[str, Any]]`

## Inputs

旧版 `search_data(query, size=None, index_names=None)`。

## Outputs

返回文档列表，保留旧通用 query 结构。

## SQL

无；读 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.search_data`

## Source

`src/kdb/retrieval/search/queries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
