# timing_auto_audit_kg.AutoAuditProcessor.check_pending_audit_docs

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, index_name: str, from_type_norm: List[str], hours: int=24, minutes: int=0`.

Behavior / Outputs: Count exact eligible records without applying retrieval defaults.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
