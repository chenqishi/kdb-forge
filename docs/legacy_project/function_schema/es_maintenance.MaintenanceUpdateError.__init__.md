# es_maintenance.MaintenanceUpdateError.__init__

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `self, kind: str, payload: Mapping=None`.

Behavior / Outputs: See implementation and auto_audit_unified_20261019 review for maintained data contract.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
