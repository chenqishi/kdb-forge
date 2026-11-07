#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-30

set -Eeo pipefail

export LC_ALL=C
config_file=${1:?missing config file}

alert_failure() {
    local message="QA Mining scheduled run failed at step: $1"
    echo "[ALERT] ${message}" >&2
    logger -t qa-mining-scheduler -- "${message}" || true
}

if ! source "$config_file"; then
    alert_failure "load_config"
    exit 1
fi

# 保存当前目录
current_dir=$(pwd)

# 切换到脚本所在目录的上一级
cd "$(dirname "$0")/../.."
end_time=$(date +"%Y%m%d%H%M%S")
root_dir=./
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
run_record_file=$root_dir/data/chatknowledge/run_timing_record.txt

# 从记录文件读取最后一行作为start_time，如果为空则使用一个月前的时间
if [ -s "$run_record_file" ]; then
    start_time=$(tail -n 1 "$run_record_file")
else
    # 获取一个月前的时间作为start_time (兼容 macOS 和 Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        start_time=$(date -v-1m +"%Y%m%d%H%M%S")
    else
        # Linux
        start_time=$(date -d "1 month ago" +"%Y%m%d%H%M%S")
    fi
fi

# 使用小时级时间做区分 (格式: YYYYMMDDHH)
end_time_hour=$(date +"%Y%m%d%H")
PYTHON=${KDB_PYTHON:-python}
flag=timing_v1_${end_time_hour}
mkdir -p data/chatknowledge/ log/

# 运行批量聊天QA挖掘请求脚本
CURRENT_STEP=batch_run_chatqa_request
if ! "$PYTHON" -m kdb.jobs.chat_mining \
    data/chatknowledge/appid_record.txt \
    config/mysql_conn_config.json \
    ${start_time} \
    ${end_time} \
    ${flag} >log/run_chatknowledge_by_request.log 2>&1; then
    alert_failure "$CURRENT_STEP"
    exit 1
fi

end_time=$(date +"%Y%m%d%H%M%S") # 重新获取当前时间，以囊括上面刚生成的知识
CURRENT_STEP=batch_gen_audit_data_and_send
if ! "$PYTHON" -m kdb.jobs.audit_reports config/chatkonwledge_report_platform_map.txt config/config_for_search_index.json data/chatknowledge ${start_time} ${end_time} $flag >log/chatknowledge_report.log 2>&1; then
    alert_failure "$CURRENT_STEP"
    exit 1
fi

# 仅当所有外层步骤成功后推进全局水位。
CURRENT_STEP=advance_global_watermark
echo "$end_time" >>"$run_record_file"
CURRENT_STEP=complete
cd "$current_dir"
