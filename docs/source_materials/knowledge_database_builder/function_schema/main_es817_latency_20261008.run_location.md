# run_location

Inputs: four approved immutable requests; label main or sg. Main is existing SSH target shenzhen-120.
Outputs: run the same small standalone standard-library probe serially, via encrypted SSH stdin on main and local subprocess stdin on sg. Low process priority, one concurrent request, 5-second idle gaps. No code/file deployment to main, no listener or online API requests. Record four response metrics/IDs and before/after snapshots; validate unchanged online retrieval PID/start/source/config and stop if load is high or memory low. At most2version+2HEAD+4search reads per location; no retries.
SQL/side effects: only bounded native ES reads and process metadata. No files written on main, git operation, installation, restart, mapping/document/alias/config update.
