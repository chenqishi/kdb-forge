# kdb.services.retrieval.app.FromTypeCountRequest.validate_index_name

## Signature

`FromTypeCountRequest.validate_index_name(cls, value)`

## Inputs

Optional string literal index.

## Outputs

Empty/null allowed; reject _all/dot/dotdot/leading +/-/_ and ES-invalid path, union, wildcard, date-math, whitespace characters and >255 UTF-8 bytes, no name translation.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
