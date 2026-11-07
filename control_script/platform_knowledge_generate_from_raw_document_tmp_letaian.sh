#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
#root_dir=$(cd $(dirname $0); pwd)
root_dir=/Users/chenqishi/stone_fish/knowledge_database_builder
export PYTHONPATH=$root_dir:$PYTHONPATH

platform_raw_dat_dir_map_file=test
data_dir=/Users/chenqishi/stone_fish/knowledge_database_builder/data/letian/20241024
log_dir=log/letian
flag=v1
dataset_map_file=test
index_config_path=/Users/chenqishi/stone_fish/knowledge_database_builder/config/config_for_search_index.json

PYTHON=python
data_file=/Users/chenqishi/stone_fish/knowledge_database_builder/data/letian/20241024/segment_getindex_v1.txt
# segment dataset
#$PYTHON $root_dir/knowledge_generate/knowlege_segment_builder_by_dify.py run_batch_get_segment_knowledge $data_dir/all_trans_to_text_${flag}.txt $flag 1 0 1 1>$data_dir/segment_getindex_${flag}.txt  2>$log_dir/segment_getindex_model_${flag}.log
#转成es格式
$PYTHON $root_dir/commons/schema_trans.py trans_segment_to_search_data_for_file --input_file=$data_dir/segment_getindex_${flag}.txt --output_file=$data_dir/segment_getindex_${flag}_search_data.txt --field_num=0  &>$log_dir/segment_getindex_${flag}_search_data.log
#插入到es中
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index  --data_file=$data_dir/segment_getindex_${flag}_search_data.txt --config_path=$index_config_path &>$log_dir/insert_segment_to_search_index_${flag}.log
# 插入fastgpt的直接去掉
#$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_segment_dataset $data_dir/segment_getindex_${flag}.txt  $dataset_map_file $api_key  &>$log_dir/build_segment_dataset_${flag}.log


