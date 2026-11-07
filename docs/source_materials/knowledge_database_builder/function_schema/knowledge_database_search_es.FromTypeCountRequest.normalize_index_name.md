# knowledge_database_search_es.FromTypeCountRequest.normalize_index_name

## Inputs
Raw request dict; index_name/indexName aliases optional, null/empty allowed.

## Outputs
Accept equal aliases; copy dict and normalize indexName, reject conflicts. Forbid extra request fields through model config.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
