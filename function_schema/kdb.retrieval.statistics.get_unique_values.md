# kdb.retrieval.statistics.get_unique_values

## Signature

`get_unique_values(self, index_name: str, field_name: str, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None) -> Union[List[str], List[Dict[str, Any]]]`

## Inputs

旧 index_name、field_name、size、include_doc_count、extra_query。

## Outputs

唯一值列表或带计数的字典列表。

## SQL

无；读 Elasticsearch terms aggregation。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_unique_values`

## Source

`src/kdb/retrieval/statistics.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
