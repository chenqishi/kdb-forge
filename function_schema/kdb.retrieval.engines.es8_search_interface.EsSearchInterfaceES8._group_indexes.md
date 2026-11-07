# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._group_indexes

## Signature

`EsSearchInterfaceES8._group_indexes(self, index_names: IndexNames) -> List[Tuple[SimpleNamespace, List[str]]]`

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

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
