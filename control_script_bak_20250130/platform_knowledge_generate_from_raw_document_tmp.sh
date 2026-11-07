#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
#root_dir=$(cd $(dirname $0); pwd)
root_dir=/Users/chenqishi/stone_fish/knowledge_database_builder
export PYTHONPATH=$root_dir:$PYTHONPATH

platform_raw_dat_dir_map_file=$1
data_dir=$2
log_dir=$3
flag=$4
api_key=$5
dataset_map_file=$6

PYTHON=python

#$PYTHON $root_dir/knowledge_clear_tool/wordtotext.py batch_dir_trans $platform_raw_dat_dir_map_file 1>$data_dir/all_trans_to_text_${flag}.txt 2>$log_dir/all_trans_to_text_${flag}.log
# translated 当前没用到，采用源文件已原地修改的方法
#$PYTHON $root_dir/knowledge_clear_tool/knowledge_translate_by_dify.py run_batch_translate_pdf_json_content $data_dir/all_trans_to_text_${flag}.txt 1>$data_dir/all_trans_to_text_${flag}_translated.txt 2>$log_dir/all_trans_to_text_${flag}_translated.log



# segment dataset
$PYTHON $root_dir/knowledge_generate/knowlege_segment_builder_by_dify.py run_batch_get_segment_knowledge $data_dir/all_trans_to_text_${flag}.txt $flag 1 0 1 1>$data_dir/segment_getindex_${flag}.txt  2>$log_dir/segment_getindex_model_${flag}.log
$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_segment_dataset $data_dir/segment_getindex_${flag}.txt  $dataset_map_file $api_key  &>$log_dir/build_segment_dataset_${flag}.log


