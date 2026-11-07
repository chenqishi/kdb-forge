# es_search_interface.EsSearchInterfaceOri.count_by_query

## Inputs
Original index_name/query; new optional require_complete=False preserves all existing default calls.

## Outputs
Legacy count unchanged by default; strict opt-in uses complete_count, rejects incomplete results. Native body count without ensure/create.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
