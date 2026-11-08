#!/bin/sh
# The historical cron passes python_env_config.sh as $1. Keep accepting that
# argument, but don't source it: it activates the retired ES7 environment.
set -eu
audit_root=$(CDPATH= cd "$(dirname "$0")/../.." && pwd)
cd "$audit_root"
export PYTHONPATH="$audit_root/src:${PYTHONPATH:-}"
audit_python=${AUTO_AUDIT_PYTHON:-${KDB_PYTHON:-python}}
audit_config=${AUTO_AUDIT_SEARCH_CONFIG:-$audit_root/config/config_for_search_index.json}
audit_index=${AUTO_AUDIT_INDEX:-all}
mkdir -p log
audit_stamp=$(date +%Y%m%d%H%M%S)
# Remain in the foreground so flock covers the entire run and cron can see its
# real exit status. Exit 75 means another run already owns the lock.
exec flock -n -E 75 log/auto_audit.lock "$audit_python" \
    -m kdb.entrypoints.scheduled.auto_audit \
    --search-config "$audit_config" --index "$audit_index" \
    --from-type-norm "document,html" --hours 24 \
    >>"log/auto_audit_all.log.$audit_stamp" 2>&1
