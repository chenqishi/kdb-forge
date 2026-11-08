# kdb.entrypoints.http.retrieval.models.FromTypeCountRequest.validate_index_name

## Signature

`validate_index_name(cls, value)`

## Inputs

Optional string literal index.

## Outputs

Empty/null allowed; reject _all/dot/dotdot/leading +/-/_ and ES-invalid path, union, wildcard, date-math, whitespace characters and >255 UTF-8 bytes, no name translation.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/entrypoints/http/retrieval/models.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
