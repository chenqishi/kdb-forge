# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._fields_query

## Signature

`_fields_query(query: Mapping[str, Any]) -> Optional[Dict[str, Any]]`

## Inputs

通用 query dict 中可选 fields。

## Outputs

match bool query 或 None。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
