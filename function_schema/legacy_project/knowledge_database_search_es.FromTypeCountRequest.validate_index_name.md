# knowledge_database_search_es.FromTypeCountRequest.validate_index_name

## Inputs
Optional string literal index.

## Outputs
Empty/null allowed; reject _all/dot/dotdot/leading +/-/_ and ES-invalid path, union, wildcard, date-math, whitespace characters and >255 UTF-8 bytes, no name translation.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
