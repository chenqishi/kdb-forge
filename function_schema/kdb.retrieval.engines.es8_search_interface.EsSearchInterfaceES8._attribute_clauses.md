# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._attribute_clauses

## Signature

`_attribute_clauses(cls, attributes: Any) -> Tuple[List[Dict[str, Any]], bool]`

## Inputs

属性 dict 或多组属性 list；`_id` 条件使用 ES8 `ids` query，列表字段使用 `terms`。

## Outputs

ES 属性过滤子句及是否显式指定 `del_flag`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
