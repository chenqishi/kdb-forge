#!/bin/bash
set -eo pipefail

config_file=${1:-/root/knowledge_database_builder/config/python_env_config.sh}
if [ $# -gt 0 ]; then
    shift
fi
if [ -f "$config_file" ]; then
    source "$config_file"
fi

cd "$(dirname "$(dirname "$0")")"
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

python control_script/chatqa_learning_daily_report.py \
    --mysql-config=config/mysql_conn_config.json \
    --report-config=config/chatkonwledge_report_platform_map.txt \
    --data-dir=data/off_task_data \
    --window-hours=24 \
    "$@"
