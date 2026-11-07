#!/bin/bash
# Copyright (c) 2024 chenqishi2019@gmail.com, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-02-06
export LC_ALL=C

data_file=$1
output_file_prefix=$2
index_config_path=$3
flag=$4
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
log_dir=${root_dir}/log
PYTHON=python

python $root_dir/commons/schema_trans.py trans_review_excel_to_json_file $data_file ${output_file_prefix}_audit_serch_json.txt synonyms_title,supply_info_query &>${log_dir}/trans_review_excel_to_json_file_${flag}.log

$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=${output_file_prefix}_audit_serch_json.txt --config_path=$index_config_path --is_update_data=1 &>${log_dir}/insert_data_to_search_index_${flag}.log