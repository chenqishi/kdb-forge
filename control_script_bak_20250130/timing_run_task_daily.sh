#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-23

export LC_ALL=C
config_file=$1
source $config_file



# 保存当前目录
current_dir=$(pwd)

# 切换到脚本所在目录的上一级
cd "$(dirname "$(dirname "$0")")"

# 获取当前时间作为end_time (格式: YYYYMMDDHHmmss)
end_time=`date +"%Y%m%d%H%M%S"`

# 获取前一天的时间作为start_time (兼容 macOS 和 Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    start_time=`date -v-1d +"%Y%m%d%H%M%S"`
else
    # Linux
    start_time=`date -d "1 days ago" +"%Y%m%d%H%M%S"`
fi

# 运行报告生成脚本
sh -x control_script/gen_static_robot_report.sh \
    data/robot_report/wait_for_robot_report.txt \
    ${start_time} \
    ${end_time} \
    data/robot_report \
    log/robot_report \
    data/robot_report/black_group_file.txt \
    v1 \
    &>log/robot_report/run_batch.log &

# 切换回原来的目录
cd "$current_dir"
