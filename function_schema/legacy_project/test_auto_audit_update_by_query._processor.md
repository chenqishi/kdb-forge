# test_auto_audit_update_by_query._processor

## 2026-10-19 unified audit integration

Source: `tests/test_auto_audit_update_by_query.py`

Inputs: `es`.

Behavior / Outputs: Offline regression boundary and assertions; no real network or business data writes.

ES / SQL: Only fake ES boundaries / isolated temporary files for pytest; readonly runner permits only guarded read requests, loads sources in memory and never deploys or starts a service.
