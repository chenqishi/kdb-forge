# Manual-tool legacy wrappers

Inputs: original argv, import namespace, cwd and environment.
Outputs: execute the single retained manual source in the original namespace; propagate return, exceptions and SystemExit unchanged.
SQL: wrapper performs no SQL itself. Queue source sends original HTTP task operations. Historical drain performs stop/soft-delete via original dependencies. Never execute either for smoke.
Locations: root `test_queue_system.py` → `tests/manual/test_queue_system.py`; root `drain_bol.py` → `archive/incident_tools/drain_bol.py`.
