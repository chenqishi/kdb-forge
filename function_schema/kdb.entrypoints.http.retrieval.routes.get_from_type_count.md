# kdb.entrypoints.http.retrieval.routes.get_from_type_count

## Signature

`get_from_type_count(request: FromTypeCountRequest)`

## Inputs

Validated FromTypeCountRequest via POST /get_from_type_count.

## Outputs

FromTypeCountResponse success/count/message. Calls actual business via asyncio.to_thread; errors logged and return success=false/count0/generic message. Empty index success0 before initialization check. No service lifespan activation or ES writes.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/entrypoints/http/retrieval/routes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
