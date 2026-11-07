# test_auto_audit_unified_20261019.matches

## 2026-10-19 unified audit integration

Source: `tests/test_auto_audit_unified_20261019.py`

Inputs: `source, query`.

Behavior / Outputs: Independent exact matcher; unsupported fixture DSL must fail loudly.

ES / SQL: Only fake ES boundaries / isolated temporary files for pytest; readonly runner permits only guarded read requests, loads sources in memory and never deploys or starts a service.
