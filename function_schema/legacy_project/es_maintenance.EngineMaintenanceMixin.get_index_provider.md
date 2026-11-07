# es_maintenance.EngineMaintenanceMixin.get_index_provider

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, index_name: str`.

Behavior / Outputs: Describe route ownership without exposing connection credentials.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
