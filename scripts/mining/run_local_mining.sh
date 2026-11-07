#!/usr/bin/env bash
# Manual entry; starts real mining. Preserve caller cwd, argv, PATH and PYTHONPATH.
kdb_candidate_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
exec "${KDB_PYTHON:-python}" "$kdb_candidate_root/run_local_mining.py" "$@"
