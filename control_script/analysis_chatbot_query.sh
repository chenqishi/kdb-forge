#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-04
export LC_ALL=C

batch_data_file=$1 #机器人\t平台\t数据地址
data_dir=$2
log_dir=$3
config_filter_query_config=$4
config_chat_config=$5
flag=$6
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
PYTHON=python
sh -x $root_dir/control_script/download_chat_and_image.sh $batch_data_file $data_dir $log_dir $flag

$PYTHON -u $root_dir/cross_broder_access/data_parse_tools.py run_batch_gen_query_form_chat_history_all $data_dir/download_file_batch_${flag}_add_image.txt 3 1>$data_dir/chatbot_query_parse_${flag}.txt  2>$log_dir/chatbot_query_parse_${flag}.log
$PYTHON -u $root_dir/cross_broder_access/add_mark.py add_mark_dify $data_dir/chatbot_query_parse_${flag}.txt $config_filter_query_config 2 1>$data_dir/chatbot_query_parse_${flag}_add_mark.txt 2>$log_dir/chatbot_query_parse_${flag}_add_mark.log
$PYTHON -u $root_dir/cross_broder_access/filter_query.py filter_query_by_mark $data_dir/chatbot_query_parse_${flag}_add_mark.txt 3 "类别1" 2 1>$data_dir/chatbot_query_parse_${flag}_add_mark_filter.txt 2>$log_dir/chatbot_query_parse_${flag}_add_mark_filter.log
$PYTHON -u $root_dir/cross_broder_access/difymodel_access.py test_one_model $data_dir/chatbot_query_parse_${flag}_add_mark_filter.txt $config_chat_config 0 2 1>$data_dir/chatbot_query_parse_${flag}_add_mark_dify.txt 2>$log_dir/chatbot_query_parse_${flag}_add_mark_dify.log
