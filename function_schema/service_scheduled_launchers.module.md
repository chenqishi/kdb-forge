# Candidate shell launchers

Inputs: argv and inherited environment/cwd. Service launchers require explicit absolute executable KDB_PYTHON (missing/invalid exits64); prepend candidate src/root to inherited PYTHONPATH, exec local preflight, then exec the original script with unchanged argv/cwd/PATH. A first --check prints safe interpreter/SDK/resource metadata and never executes a service. Invalid prerequisites exit78. No implicit shared/PATH Python is selected; test-only private SDK is never silently injected into runtime. Scheduled launchers exec the retained original shell script, which retains its own cwd/interpreter/PYTHONPATH/locks/logging/exit semantics.
Outputs: original exit status and signal delivery through exec. No launcher runs automatically.
SQL: no direct SQL; downstream original entry side effects remain.

Manual mining launcher: scripts/mining/run_local_mining.sh execs root run_local_mining.py with KDB_PYTHON/PATH python, preserving cwd, argv, PYTHONPATH and downstream shim behavior. It starts real work and was not executed.
