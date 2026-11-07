# kdb.retrieval.application.search_index_data_interface.SearchEngine.count_by_query

## Signature

`SearchEngine.count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool=False) -> int`

## Inputs

index_name/query/require_complete=False.

## Outputs

Protocol declaration for native engine count, int; strict failures propagate.

## SQL

None. Only native Elasticsearch/OpenSearch _count reads.

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
