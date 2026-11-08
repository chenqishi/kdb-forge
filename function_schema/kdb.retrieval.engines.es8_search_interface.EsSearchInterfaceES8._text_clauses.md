# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._text_clauses

## Signature

`_text_clauses(query: Mapping[str, Any]) -> List[Dict[str, Any]]`

## Inputs

通用 query dict 中的 query 文本。

## Outputs

BM25 `multi_match` 与 synonym `match` 子句。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
