# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.get_from_type_count

## Signature

`SearchDataInterface.get_from_type_count(self, index_name: Optional[str], from_type: str='chat_auto', start: Optional[datetime]=None, end: Optional[datetime]=None) -> int`

## Inputs

index_name optional/empty; from_type default chat_auto; start/end optional naive datetime.

## Outputs

0 for empty index without ES calls, otherwise strict native count(high AND exact from_type). Only both dates add inclusive insert_time range; start>end returns native0. No del/audit/type/category/default-index/source/embedding/LLM or ensure.

 Serialize naive datetimes with isoformat(space, seconds) to preserve four-digit year0001 and Java normal local formatting.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
