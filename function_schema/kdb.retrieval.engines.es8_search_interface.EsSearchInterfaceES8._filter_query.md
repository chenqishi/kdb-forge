# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._filter_query

## Signature

`_filter_query(cls, query: Mapping[str, Any], include_default_del_flag: bool=True) -> Dict[str, Any]`

## Inputs

通用 query dict、是否自动加 `del_flag=0`。

## Outputs

可放入 ES8 bool.must 的 filter query。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
