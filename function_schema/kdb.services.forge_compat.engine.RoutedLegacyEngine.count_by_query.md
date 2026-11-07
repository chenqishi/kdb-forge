# kdb.services.forge_compat.engine.RoutedLegacyEngine.count_by_query

## Signature

`RoutedLegacyEngine.count_by_query(self, index_name, query, require_complete=False)`

## Inputs

Original forge `index_name, query, require_complete=False`. Native DSL is passed through unchanged.

## Outputs

For ordinary count, delegate directly to published ES8 method. For forge strict count only, retain original SDK flags ignore_unavailable=False, allow_no_indices=False, expand_wildcards="none", then use the published complete_count validator. No new query construction or retrieval algorithm. Same provider binding as published engine.

## SQL

None. Only native Elasticsearch count request; no ensure/index writes.

## Source

`src/kdb/services/forge_compat/engine.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
