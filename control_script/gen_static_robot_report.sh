#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2025-01-22
export LC_ALL=C

batch_data_file=$1 #机器人\t类型公众号/微信\t平台\t通知id\t发送url\t数据地址
start_time=$2
end_time=$3
data_dir=$4
log_dir=$5
black_groups_file=$6
flag=$7
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
PYTHON=python


$PYTHON $root_dir/data_control_tools/remote_machine_tools.py run_batch_download_files \
    --batch_file_path=$batch_data_file \
    --output_file_path=$data_dir/download_file_batch_${flag}.txt \
    --save_data_dir=$data_dir \
    --remote_field_num=5 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/7b28ae074cd702826283.value")" \
    --port=22


$PYTHON $root_dir/static_report/robot_answer_static.py run_batch_robot_static_report\
    --input_file=$data_dir/download_file_batch_${flag}.txt \
    --start_time=$start_time \
    --end_time=$end_time \
    --data_field=6 \
    --black_groups_file=$black_groups_file \
    --output_file=$data_dir/robot_answer_static_report_${flag}.txt
