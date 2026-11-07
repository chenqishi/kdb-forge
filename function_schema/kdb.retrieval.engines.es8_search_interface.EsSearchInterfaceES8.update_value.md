# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.update_value

## Signature

`EsSearchInterfaceES8.update_value(self, index_name: IndexNames, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool`

## References

Elastic 8.17 docs-update/docs-bulk/docs-update-by-query; Aliyun script-whitelist; old EsSearchInterfaceOri.update_value/update_by_query.

## Inputs

索引、更新字段和条件列表。

## Outputs

所有目标索引通过 ES8 `update_by_query(query=..., script=...)` 按条件更新成功返回 True。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
