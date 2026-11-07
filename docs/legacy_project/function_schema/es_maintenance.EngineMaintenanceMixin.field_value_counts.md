# es_maintenance.EngineMaintenanceMixin.field_value_counts

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, index_name: str, field: str, query: Dict[str, Any], size: int=10`.

Behavior / Outputs: Return complete bounded terms counts, rejecting shard errors/truncation.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
