# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._build_es_query

## Signature

`_build_es_query(self, query: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

旧通用 query。

## Outputs

ES8 query DSL；不包含 ES7 body 包装或 script_score。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
