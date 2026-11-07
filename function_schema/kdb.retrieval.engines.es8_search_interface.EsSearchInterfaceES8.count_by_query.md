# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.count_by_query

## Signature

`EsSearchInterfaceES8.count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

Original index_name/query; optional require_complete=False for common engine protocol.

## Outputs

Original shard retry behavior retained; strict opt-in complete_count before returning. Client chosen by unchanged physical index, no ensure/create.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
