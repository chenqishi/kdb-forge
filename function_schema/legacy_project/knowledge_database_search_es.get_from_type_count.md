# knowledge_database_search_es.get_from_type_count

## Inputs
Validated FromTypeCountRequest via POST /get_from_type_count.

## Outputs
FromTypeCountResponse success/count/message. Calls actual business via asyncio.to_thread; errors logged and return success=false/count0/generic message. Empty index success0 before initialization check. No service lifespan activation or ES writes.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
