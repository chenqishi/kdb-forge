#!/usr/bin/env bash
# Explicit interpreter; preserve the caller's cwd/argv/PATH and inherited PYTHONPATH.
kdb_candidate_root="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
if [[ -z "${KDB_PYTHON:-}" || "$KDB_PYTHON" != /* || ! -x "$KDB_PYTHON" ]]; then
  printf '%s\n' 'Set KDB_PYTHON to an explicit absolute executable for this service; use --check first. No PATH python is selected automatically.' >&2
  exit 64
fi
export PYTHONPATH="$kdb_candidate_root/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$KDB_PYTHON" "$kdb_candidate_root/scripts/services/preflight.py" fastgpt_proxy "$@"
