# es_maintenance.EngineMaintenanceMixin.configure_maintenance_updates

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, scroll_size: int=30, request_timeout_seconds: int=3600`.

Behavior / Outputs: Apply explicit batching only to a maintenance factory instance.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
