# es_maintenance.EngineMaintenanceMixin.close

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self`.

Behavior / Outputs: Release the legacy connection pool; ES8 retains its existing close().

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
