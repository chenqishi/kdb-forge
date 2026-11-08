# kdb.retrieval.engines.protocol.SearchEngine.count_by_query

## Signature

`count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

index_name/query/require_complete=False.

## Outputs

Protocol declaration for native engine count, int; strict failures propagate.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/protocol.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
