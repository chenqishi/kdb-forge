# timing_auto_audit_kg.AutoAuditProcessor.auto_audit_for_indexes

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, index_names: List[str], from_type_norm: List[str], hours: int=24, minutes: int=0, batch_size: int=50, scroll_size: int=30, dry_run: bool=False`.

Behavior / Outputs: Report every failure/partial update instead of claiming overall success.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
