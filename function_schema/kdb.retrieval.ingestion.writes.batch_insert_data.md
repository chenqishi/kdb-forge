# kdb.retrieval.ingestion.writes.batch_insert_data

## Signature

`batch_insert_data(self, data_list: List[Dict[str, Any]], check_duplicate: bool=True) -> List[bool]`

## Inputs

旧版 `data_list` 和 `check_duplicate`。

## Outputs

按旧顺序返回每条 `insert_data` 的结果列表。

## SQL

无；写 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.batch_insert_data`

## Source

`src/kdb/retrieval/ingestion/writes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
