# timing_auto_audit_kg.load_engine_config_path

## 2026-10-19 unified audit integration

Source: `control_script/timing_auto_audit_kg.py`

Inputs: `config_path: Optional[str], search_config_path: Optional[str]`.

Behavior / Outputs: Resolve exactly one existing config; follow the same service pointer.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
