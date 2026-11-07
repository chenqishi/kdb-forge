# kdb.services.retrieval.app.get_from_type_count

## Signature

`get_from_type_count(request: FromTypeCountRequest)`

## Inputs

Validated FromTypeCountRequest via POST /get_from_type_count.

## Outputs

FromTypeCountResponse success/count/message. Calls actual business via asyncio.to_thread; errors logged and return success=false/count0/generic message. Empty index success0 before initialization check. No service lifespan activation or ES writes.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
