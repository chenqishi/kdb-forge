# kdb.entrypoints.http.retrieval.models.FromTypeCountRequest.validate_local_time

## Signature

`validate_local_time(cls, value)`

## Inputs

start/end None, local datetime or yyyy-MM-dd HH:mm:ss string.

## Outputs

Naive datetime with second precision; invalid/date-only/timezone input rejected. No implicit timezone conversion.

 Validate exact four-digit year using regex then strptime (including year0001); do not compare Linux strftime which omits leading zeros.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/entrypoints/http/retrieval/models.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
