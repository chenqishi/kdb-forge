# snapshot

Inputs/Outputs: reuse exact snapshot function from previously read tests/main_es817_latency_20261008.py and its snapshot schema; retrieval PIDs/startticks/cwd/source hashes, load/cpu/MemAvailable. SQL/side effects: metadata only. Additional guards live in run_probe rather than modifying reused function.
