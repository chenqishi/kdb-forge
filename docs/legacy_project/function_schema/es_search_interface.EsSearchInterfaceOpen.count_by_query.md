# es_search_interface.EsSearchInterfaceOpen.count_by_query

## Inputs
index_name/query and optional require_complete=False; newly expose native OpenSearch count.

## Outputs
Native body count, strict completeness opt-in. No ensure or mutation.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
