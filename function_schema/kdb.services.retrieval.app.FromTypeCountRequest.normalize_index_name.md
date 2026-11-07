# kdb.services.retrieval.app.FromTypeCountRequest.normalize_index_name

## Signature

`FromTypeCountRequest.normalize_index_name(cls, values)`

## Inputs

Raw request dict; index_name/indexName aliases optional, null/empty allowed.

## Outputs

Accept equal aliases; copy dict and normalize indexName, reject conflicts. Forbid extra request fields through model config.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/services/retrieval/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
