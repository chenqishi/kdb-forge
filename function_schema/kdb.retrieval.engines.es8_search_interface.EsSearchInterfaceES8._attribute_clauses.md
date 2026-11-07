# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._attribute_clauses

## Signature

`EsSearchInterfaceES8._attribute_clauses(cls, attributes: Any) -> Tuple[List[Dict[str, Any]], bool]`

## Inputs

属性 dict 或多组属性 list；`_id` 条件使用 ES8 `ids` query，列表字段使用 `terms`。

## Outputs

ES 属性过滤子句及是否显式指定 `del_flag`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
