# timing_auto_audit_kg.AutoAuditProcessor.__init__

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `self, config_path: Optional[str]=None, *, search_config_path: Optional[str]=None, engine: Any=None, now: Optional[datetime]=None`.

Behavior / Outputs: See implementation and auto_audit_unified_20261019 review for maintained data contract.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
