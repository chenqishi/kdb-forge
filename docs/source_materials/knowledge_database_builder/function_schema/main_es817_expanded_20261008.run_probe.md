# run_probe

Inputs: encrypted in-memory configs/sources/cases. Outputs: preflight twoES8versions/fourHEAD; stages1thread37,2threads37,4threads74 =148logical queries<=592search reads normally. Monitor before/after and per-case snapshots: load1 limit CPU*0.5, MemAvailable>=4GiB, existing online PIDs/start/source unchanged; low priority process, maximum4worker threads, no listener. Close connections. Stream sanitized progress and final JSON. SQL/side effects: read-only new ES8 and /proc, no oldqueries, no API calls, no writes remote.
