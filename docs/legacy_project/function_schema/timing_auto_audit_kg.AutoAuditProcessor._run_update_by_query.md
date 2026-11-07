# timing_auto_audit_kg.AutoAuditProcessor._run_update_by_query

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, index_name: str, query: Dict[str, Any], update_fields: Dict[str, Any], scroll_size: int, request_timeout_seconds: int=3600`.

Behavior / Outputs: Pass assignments to the same engine used by other data operations.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
