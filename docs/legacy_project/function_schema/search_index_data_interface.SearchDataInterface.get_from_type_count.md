# search_index_data_interface.SearchDataInterface.get_from_type_count

## Inputs
index_name optional/empty; from_type default chat_auto; start/end optional naive datetime.

## Outputs
0 for empty index without ES calls, otherwise strict native count(high AND exact from_type). Only both dates add inclusive insert_time range; start>end returns native0. No del/audit/type/category/default-index/source/embedding/LLM or ensure.

 Serialize naive datetimes with isoformat(space, seconds) to preserve four-digit year0001 and Java normal local formatting.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
