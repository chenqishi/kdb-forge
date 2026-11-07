# timing_auto_audit_kg.AutoAuditProcessor._queries

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, from_type_norm: List[str], hours: int, minutes: int`.

Behavior / Outputs: Build the original three rules using one fixed run eligibility time.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
