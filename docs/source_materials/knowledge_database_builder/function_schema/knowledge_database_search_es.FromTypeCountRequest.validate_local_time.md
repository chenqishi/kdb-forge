# knowledge_database_search_es.FromTypeCountRequest.validate_local_time

## Inputs
start/end None, local datetime or yyyy-MM-dd HH:mm:ss string.

## Outputs
Naive datetime with second precision; invalid/date-only/timezone input rejected. No implicit timezone conversion.

 Validate exact four-digit year using regex then strptime (including year0001); do not compare Linux strftime which omits leading zeros.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
