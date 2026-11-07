# kdb.retrieval.engines.es_search_interface.EsSearchInterfaceOri.count_by_query

## Signature

`EsSearchInterfaceOri.count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

Original index_name/query; new optional require_complete=False preserves all existing default calls.

## Outputs

Legacy count unchanged by default; strict opt-in uses complete_count, rejects incomplete results. Native body count without ensure/create.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/es_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
