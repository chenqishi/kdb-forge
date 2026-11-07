# es_maintenance.EngineMaintenanceMixin.get_all_indexes

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, exclude_system: bool=True`.

Behavior / Outputs: Inventory every provider, retaining only indexes owned by that route.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
