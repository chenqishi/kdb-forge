# timing_auto_audit_kg.AutoAuditProcessor.auto_audit_documents

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, index_name: str, from_type_norm: List[str], hours: int=24, minutes: int=0, batch_size: int=100, scroll_size: int=30, dry_run: bool=False`.

Behavior / Outputs: Apply only the original two assignments and verify the remaining set.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
