# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._group_indexes

## Signature

`_group_indexes(self, index_names: IndexNames) -> List[Tuple[SimpleNamespace, List[str]]]`

## Inputs / Outputs

Normalize string/list indexes and bind every member, preserving contiguous provider groups and original A/B/C order. Enabled mapping guards remain strict.

## SQL

None.

无。

## Requests

Bind each index exactly once per grouping call; reuse the already validated first binding without a second HEAD.

## Inputs

索引参数。

## Outputs

按 provider 分组的 `(client_binding, index_names)` 列表。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
