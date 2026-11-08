# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._impl_for

## Signature

`_impl_for(self, index_name: str) -> SimpleNamespace`

## Inputs / Outputs

Bind one exact physical index to its routed ES8 client. Only cache after any enabled index creation/mapping guard succeeds; a failed first operation must remain retryable.

## SQL

None.

无。

## Cached index lifecycle

For a cached binding with ensure enabled, confirm existence before each operation; if missing, invalidate creation/mapping caches and recreate the same physical name. If the existence request itself errors, log it and let actual online per-route query retry/fallback handle availability, keeping mapping guard errors strict on new bindings.

## Inputs

单个 index 名。

## Outputs

缓存该 index 对应的 ES8 client binding，不构造旧 `EsSearchInterfaceOri`。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
