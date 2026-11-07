# kdb.retrieval.engines.es_count_utils.complete_count

## Signature

`complete_count(response: Mapping) -> int`

## Inputs

ES native _count response Mapping from ES7/OpenSearch body or ES8 normalized body.

## Outputs

Nonnegative integer exact count; RuntimeError for malformed count, failed/incomplete shards, nonempty top-level/shard failures/error, zero-shard response (literal physical index must have shards), timed_out/terminated_early present with anything other than False. No client calls, no writes.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/es_count_utils.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
