# es_maintenance.EngineMaintenanceMixin._maintenance_client

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, index_name: str`.

Behavior / Outputs: Select the same connection as retrieval without ensure/create.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
