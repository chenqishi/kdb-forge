#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-02
export LC_ALL=C

root_dir=/Users/chenqishi/stone_fish/knowledge_database_builder
process_file=$1
data_dir=$2
log_dir=$3
flag=$4
api_key=$5
dataset_map_file=$6

PYTHON=python

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py excel_to_qa_json $process_file 1>$data_dir/excel_to_qa_json_${flag}.txt 2>$log_dir/excel_to_qa_json_${flag}.log
$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_qa_dataset $data_dir/excel_to_qa_json_${flag}.txt $dataset_map_file $api_key 0 &>$log_dir/batch_add_qa_dataset_${flag}.log
