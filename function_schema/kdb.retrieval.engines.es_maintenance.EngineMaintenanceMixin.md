# kdb.retrieval.engines.es_maintenance.EngineMaintenanceMixin

## Inputs

Inherited by the existing ES7, OpenSearch and ES8 engine implementations. Public methods: `get_all_indexes(exclude_system=True)`, `index_exists(index_name)`, `get_index_provider(index_name)`, `field_value_counts(index_name, field, query, size=10)`, `configure_maintenance_updates(scroll_size=30, request_timeout_seconds=3600)`, `close()`.

## Outputs

Routed physical-index inventory, existence boolean, provider name and complete terms counts. Configuration affects only an explicitly maintenance-mode instance; default online engine behavior stays unchanged. Fail closed on malformed/partial responses. Close all opened clients.

## SQL / ES

Only `_cat/indices`, HEAD, size=0 aggregation reads. No create/mapping calls. No SQL. Index inventory filters each provider by the same Router ownership, excludes system indexes only when requested and never silently omits a failed provider. Inventory does not authorize writing every listed index.

## Source

`src/kdb/retrieval/engines/es_maintenance.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
