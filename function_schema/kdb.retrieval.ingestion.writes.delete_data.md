# kdb.retrieval.ingestion.writes.delete_data

## Signature

`delete_data(self, data_id: str, index_names: Optional[Union[str, List[str]]]=None, refresh: bool=False) -> bool`

## Inputs

旧 `data_id, index_names=None, refresh=False`。

## Outputs

删除是否成功。

## SQL

无；写 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.delete_data`

## Source

`src/kdb/retrieval/ingestion/writes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
