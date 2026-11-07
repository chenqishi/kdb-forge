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
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/179cd7fc1fea864713b9.value")" \
    --port=22

$PYTHON $root_dir/chatknowledge/gen_knowledge_from_chat.py run_batch_robot_chat_data \
    --data_file=$data_dir/download_file_batch_${flag}.txt \
    --output_dir=$data_dir \
    --data_file_field_num=3 \
    --robot_room_type_config_file=$robot_room_type_config \
    --robot_process_record_file=$robot_room_process_record \
    --robot_white_list_file=$robot_room_white_name \
    --filter_group_name=${filter_group_name} \
    --flag=$flag 1>$data_dir/chatknowledege_extract_qa_batch_${flag}.txt 2>${log_dir}/run_batch_robot_chat_data_${flag}.log
##exit 0
$PYTHON $root_dir/quality_tools/qa_quality_tools.py run_batch_add_dify_quality_and_resplit \
    --input_file=$data_dir/chatknowledege_extract_qa_batch_${flag}.txt \
    --output_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt \
    --process_field_num=4 \
    --dify_qa_filter_name=chatknowledge_qa_filter \
    --flag=$flag &>${log_dir}/run_batch_add_dify_quality_and_resplit_${flag}.log

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_split_json_quality_to_excel \
    --batch_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt \
    --platform_field_num=1 \
    --high_quality_excel_file=$data_dir/high_quality_${flag}.xlsx \
    --mid_quality_excel_file=$data_dir/mid_quality_${flag}.xlsx \
    --low_quality_excel_file=$data_dir/low_quality_${flag}.xlsx \
    --field_num=5 2>$log_dir/batch_split_json_quality_to_excel_${flag}.log

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_select_high_quality_qa_and_white_answer_to_json \
    --batch_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt \
    --white_name_file=${white_write_name_file} \
    --field_num=5 1>$data_dir/high_quality_for_qa_and_white_answer_json_${flag}.txt 2>$log_dir/batch_select_high_quality_qa_and_white_answer_to_json_${flag}.log

$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_qa_dataset \
    --data_from_type=chat_mining \
    --local_file_path=$data_dir/high_quality_for_qa_and_white_answer_json_${flag}.txt \
    --dataset_info_map_file=${dataset_map_file} \
    --api_key=${api_key} \
    --start_index=0 &>$log_dir/batch_add_segment_qa_dataset_${flag}.log
