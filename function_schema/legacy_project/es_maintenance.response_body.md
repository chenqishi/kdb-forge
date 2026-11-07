# es_maintenance.response_body

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_maintenance.py`

Inputs: `response: Any`.

Behavior / Outputs: Unwrap real ES8 responses without accepting an unknown success envelope.

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
