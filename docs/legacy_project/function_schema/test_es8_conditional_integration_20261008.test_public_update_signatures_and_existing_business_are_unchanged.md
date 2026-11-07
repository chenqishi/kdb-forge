# test_public_update_signatures_and_existing_business_are_unchanged

Inputs/Outputs: Compare engine public update signatures and SHA256 of factory/business/service/Router with recorded current-root baseline. Engine implementation may differ; protected caller files and original signatures must match exactly. Read-only local files only.
SQL and persistent side effects: none.

## 2026-10-19 unified audit integration

Source: `tests/test_es8_conditional_integration_20261008.py`

Inputs: ``.

Behavior / Outputs: Offline regression boundary and assertions; no real network or business data writes.

ES / SQL: Only fake ES boundaries / isolated temporary files for pytest; readonly runner permits only guarded read requests, loads sources in memory and never deploys or starts a service.
