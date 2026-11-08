# kdb.retrieval.engines.providers.es7.EsSearchInterfaceOri.count_by_query

## Signature

`count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

Original index_name/query; new optional require_complete=False preserves all existing default calls.

## Outputs

Legacy count unchanged by default; strict opt-in uses complete_count, rejects incomplete results. Native body count without ensure/create.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/providers/es7.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
