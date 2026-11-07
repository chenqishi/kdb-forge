# es8_search_interface.EsSearchInterfaceES8.count_by_query

## Inputs
Original index_name/query; optional require_complete=False for common engine protocol.

## Outputs
Original shard retry behavior retained; strict opt-in complete_count before returning. Client chosen by unchanged physical index, no ensure/create.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
