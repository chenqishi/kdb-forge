# es_count_utils.complete_count

## Inputs
ES native _count response Mapping from ES7/OpenSearch body or ES8 normalized body.

## Outputs
Nonnegative integer exact count; RuntimeError for malformed count, failed/incomplete shards, nonempty top-level/shard failures/error, zero-shard response (literal physical index must have shards), timed_out/terminated_early present with anything other than False. No client calls, no writes.

## SQL
None. Only native Elasticsearch/OpenSearch _count reads.
