# kdb.retrieval.engines.es_search_interface.EsSearchInterfaceOpen.count_by_query

## Signature

`EsSearchInterfaceOpen.count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

index_name/query and optional require_complete=False; newly expose native OpenSearch count.

## Outputs

Native body count, strict completeness opt-in. No ensure or mutation.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/engines/es_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
