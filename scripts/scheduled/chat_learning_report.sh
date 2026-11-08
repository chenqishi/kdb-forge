#!/bin/bash
set -eo pipefail

config_file=${1:-${KDB_ENV_FILE:-}}
if [ $# -gt 0 ]; then
    shift
fi
if [ -n "$config_file" ] && [ -f "$config_file" ]; then
    source "$config_file"
fi

cd "$(dirname "$0")/../.."
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"

"${KDB_PYTHON:-python}" -m kdb.entrypoints.scheduled.learning_report \
    --mysql-config=config/mysql_conn_config.json \
    --report-config=config/chatkonwledge_report_platform_map.txt \
    --data-dir=data/off_task_data \
    --window-hours=24 \
    "$@"
