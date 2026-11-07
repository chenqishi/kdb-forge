#!/bin/bash
# Copyright (c) 2023 chenqishi, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2024-12-12
export LC_ALL=C

batch_data_file=$1 #机器人\t平台\t数据地址
robot_room_type_config=$2 #机器人\t群名\t平台\t类型(转发/普通群)
robot_room_process_record=$3 #机器人\t群名\t时间
robot_room_white_name=$4 #机器人\t群名\t白名单
data_dir=$5
log_dir=$6
flag=$7
white_write_name_file=$8
filter_group_name=$9
index_config_path=${10}
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
PYTHON=python
prompt_file_map_file=$root_dir/config/prompt_file_map.txt
touch $prompt_file_map_file
$PYTHON $root_dir/data_control_tools/remote_machine_tools.py run_batch_download_files \
    --batch_file_path=$batch_data_file \
    --output_file_path=$data_dir/download_file_batch_${flag}.txt \
    --save_data_dir=$data_dir \
    --remote_field_num=2 \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/93cf7057a8b4887b3f13.value")" \
    --port=22

$PYTHON $root_dir/chatknowledge/gen_knowledge_from_chat.py run_batch_robot_chat_data \
    --data_file=$data_dir/download_file_batch_${flag}.txt \
    --output_dir=$data_dir \
    --data_file_field_num=3 \
    --robot_room_type_config_file=$robot_room_type_config \
    --robot_process_record_file=$robot_room_process_record \
    --robot_white_list_file=$robot_room_white_name \
    --filter_group_name=${filter_group_name} \
    --prompt_file_map=$prompt_file_map_file \
    --flag=$flag 1>$data_dir/chatknowledege_extract_qa_batch_${flag}.txt 2>${log_dir}/run_batch_robot_chat_data_${flag}.log
##exit 0
$PYTHON $root_dir/quality_tools/qa_quality_tools.py run_batch_add_dify_quality_and_resplit \
    --input_file=$data_dir/chatknowledege_extract_qa_batch_${flag}.txt \
    --output_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt \
    --process_field_num=4 \
    --dify_qa_filter_name=chatknowledge_qa_filter_for_chathistory \
    --flag=$flag &>${log_dir}/run_batch_add_dify_quality_and_resplit_${flag}.log

#schema处理成 es 插入格式 ${data_dir}/all_reclear_qa_file.txt
$PYTHON $root_dir/commons/schema_trans.py batch_trans_qa_to_search_data --batch_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt --output_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}_search_data.txt --field_num=5 --platform_field_num=1 --from_type="chat_auto" &>$log_dir/chatknowledege_extract_qa_quality_batch_${flag}_search_data.log
exit 0
#插入到es中
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}_search_data.txt    --config_path=$index_config_path  --is_only_title=true &>$log_dir/insert_chatknowledege_extract_qa_quality_batch_${flag}_search_data_to_search_index_${flag}.log
exit 0
# 后面的暂时没想好要不要，先放弃

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_split_json_quality_to_excel \
    --batch_file=$data_dir/chatknowledege_extract_qa_quality_batch_${flag}.txt \
    --platform_field_num=1 \
    --high_quality_excel_file=$data_dir/high_quality_${flag}.xlsx \
    --mid_quality_excel_file=$data_dir/mid_quality_${flag}.xlsx \
    --low_quality_excel_file=$data_dir/low_quality_${flag}.xlsx \
    --field_num=5 2>$log_dir/batch_split_json_quality_to_excel_${flag}.log

: ' fastgpt的直接去掉
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
'
