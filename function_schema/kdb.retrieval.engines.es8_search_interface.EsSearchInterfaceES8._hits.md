# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._hits

## Signature

`_hits(response: Mapping[str, Any], include_index: bool=False) -> List[Dict[str, Any]]`

## Inputs

ES search response。

## Outputs

旧上层兼容的 `[{_id, score, **_source}]` 列表。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
