# kdb.entrypoints.http.retrieval.models.FromTypeCountRequest.normalize_index_name

## Signature

`normalize_index_name(cls, values)`

## Inputs

Raw request dict; index_name/indexName aliases optional, null/empty allowed.

## Outputs

Accept equal aliases; copy dict and normalize indexName, reject conflicts. Forbid extra request fields through model config.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/entrypoints/http/retrieval/models.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
