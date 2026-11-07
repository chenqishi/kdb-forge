# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.update_by_query

## Signature

`EsSearchInterfaceES8.update_by_query(self, index_name: IndexNames, query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int=500) -> Dict[str, Any]`

## References

Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## Inputs

目标索引、query、更新字段、requests_per_second。

## Outputs

合并后的 updated/total/version_conflicts/failures。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
