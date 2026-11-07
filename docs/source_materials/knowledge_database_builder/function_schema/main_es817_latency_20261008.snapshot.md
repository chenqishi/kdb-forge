# snapshot (embedded standalone remote probe)

Inputs: /proc and actual retrieval process source/config paths on the current machine.
Outputs: retrieval PIDs/start ticks, cwd, source/config hashes, load and available memory. Only metadata/hashes; no arguments or credentials in output.
SQL/side effects: local read only; no service calls or mutations.
