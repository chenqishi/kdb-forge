# timing_auto_audit_kg.AutoAuditProcessor.get_all_indexes

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, exclude_system: bool=True`.

Behavior / Outputs: Use the unified inventory, including every authoritative provider.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
