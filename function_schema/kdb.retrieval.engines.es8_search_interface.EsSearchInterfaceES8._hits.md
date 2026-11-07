# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._hits

## Signature

`EsSearchInterfaceES8._hits(response: Mapping[str, Any], include_index: bool=False) -> List[Dict[str, Any]]`

## Inputs

ES search response。

## Outputs

旧上层兼容的 `[{_id, score, **_source}]` 列表。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
