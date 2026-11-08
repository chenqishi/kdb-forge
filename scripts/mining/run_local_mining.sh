#!/bin/sh
set -eu
kdb_project_root=$(CDPATH= cd "$(dirname "$0")/../.." && pwd)
export PYTHONPATH="$kdb_project_root/src:${PYTHONPATH:-}"
exec "${KDB_PYTHON:-python}" -m kdb.mining.tasks.submission.local_batch "$@"
