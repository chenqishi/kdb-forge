# test_auto_audit_unified_20261019.test_legacy_real_factory_maintenance_and_original_mode

## 2026-10-19 unified audit integration

Source: `tests/test_auto_audit_unified_20261019.py`

Inputs: `monkeypatch, tmp_path, version`.

Behavior / Outputs: Offline regression boundary and assertions; no real network or business data writes.

ES / SQL: Only fake ES boundaries / isolated temporary files for pytest; readonly runner permits only guarded read requests, loads sources in memory and never deploys or starts a service.
