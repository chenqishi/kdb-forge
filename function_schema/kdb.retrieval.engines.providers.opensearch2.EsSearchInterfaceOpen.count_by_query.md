# kdb.retrieval.engines.providers.opensearch2.EsSearchInterfaceOpen.count_by_query

## Signature

`count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

index_name/query and optional require_complete=False; newly expose native OpenSearch count.

## Outputs

Native body count, strict completeness opt-in. No ensure or mutation.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/providers/opensearch2.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
