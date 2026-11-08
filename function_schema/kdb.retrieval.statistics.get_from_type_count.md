# kdb.retrieval.statistics.get_from_type_count

## Signature

`get_from_type_count(self, index_name: Optional[str], from_type: str='chat_auto', start: Optional[datetime]=None, end: Optional[datetime]=None) -> int`

## Inputs

index_name optional/empty; from_type default chat_auto; start/end optional naive datetime.

## Outputs

0 for empty index without ES calls, otherwise strict native count(high AND exact from_type). Only both dates add inclusive insert_time range; start>end returns native0. No del/audit/type/category/default-index/source/embedding/LLM or ensure.

 Serialize naive datetimes with isoformat(space, seconds) to preserve four-digit year0001 and Java normal local formatting.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_from_type_count`

## Source

`src/kdb/retrieval/statistics.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
