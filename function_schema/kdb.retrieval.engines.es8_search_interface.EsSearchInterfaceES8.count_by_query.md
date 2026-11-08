# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.count_by_query

## Signature

`count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

Original index_name/query; optional require_complete=False for common engine protocol.

## Outputs

Original shard retry behavior retained; strict opt-in complete_count before returning. Client chosen by unchanged physical index, no ensure/create.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
