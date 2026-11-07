# kdb.services.retrieval.app.FromTypeCountRequest.validate_local_time

## Signature

`FromTypeCountRequest.validate_local_time(cls, value)`

## Inputs

start/end None, local datetime or yyyy-MM-dd HH:mm:ss string.

## Outputs

Naive datetime with second precision; invalid/date-only/timezone input rejected. No implicit timezone conversion.

 Validate exact four-digit year using regex then strptime (including year0001); do not compare Linux strftime which omits leading zeros.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
