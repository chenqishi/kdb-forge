#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-12
export LC_ALL=C

batch_data_file=$1 #机器人\t平台\t数据地址
robot_room_type_config=$2 #机器人\t群名\t平台\t类型(转发/普通群)
robot_room_process_record=$3 #机器人\t群名\t时间
robot_room_white_name=$4 #机器人\t群名\t白名单
data_dir=$5
log_dir=$6
flag=$7
api_key=$8
dataset_map_file=$9
white_write_name_file=${10}
filter_group_name=${11}
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
PYTHON=python

$PYTHON $root_dir/data_control_tools/remote_machine_tools.py run_batch_download_files \
    --batch_file_path=$batch_data_file \
    --output_file_path=$data_dir/download_file_batch_${flag}.txt \
    --save_data_dir=$data_dir \
    --remote_field_num=2 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/5f4f4360f8f48f2a60e7.value")" \
    --port=22


python $root_dir/data_control_tools/remote_machine_tools.py run_batch_process_message \
    --input_file_path=$data_dir/download_file_batch_${flag}.txt \
    --output_file_path=$data_dir/download_file_batch_${flag}_add_image.txt \
    --save_image_dir=$data_dir/image_down \
    --remote_field_num=2 \
    --local_field_num=3 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/f108a3ab2e230d18ca5d.value")" \
    --port=22
 

$PYTHON $root_dir/chatknowledge/gen_image_knowledge_from_chat.py run_batch_robot_chat_data \
    --data_file=$data_dir/download_file_batch_${flag}_add_image.txt \
    --output_dir=$data_dir \
    --data_file_field_num=3 \
    --robot_room_type_config_file=$robot_room_type_config \
    --robot_process_record_file=$robot_room_process_record \
    --robot_white_list_file=$robot_room_white_name \
    --filter_group_name=${filter_group_name} \
    --flag=$flag 1>$data_dir/chatknowledege_extract_qa_batch_${flag}.txt 2>${log_dir}/run_batch_robot_chat_data_${flag}.log