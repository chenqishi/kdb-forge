# kdb.retrieval.search.queries.get_data_by_id

## Signature

`get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]`

## Inputs

data_id。

## Outputs

文档或 None。

## SQL

无；读 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_data_by_id`

## Source

`src/kdb/retrieval/search/queries.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
