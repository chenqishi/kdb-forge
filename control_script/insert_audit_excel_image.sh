#!/bin/bash
# Copyright (c) 2024 chenqishi2019@gmail.com, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-02-06
export LC_ALL=C

data_file=$1
data_dir=$2
index_config_path=$3
flag=$4

root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
log_dir=${root_dir}/log
PYTHON=python
. "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/80789f2f61dacb89f74c.sh"

$PYTHON $root_dir/commons/schema_trans.py trans_review_excel_to_json_file "$data_file" "${data_dir}/audit_serch_json_${flag}.txt" synonyms_title,supply_info_query "$data_dir" &>"${log_dir}/trans_review_excel_to_json_file_${flag}.log"

$PYTHON $root_dir/commons/image_data_tools.py process_search_data_image_file "${data_dir}/audit_serch_json_${flag}.txt" "$api_key" 1>"${data_dir}/audit_search_image_processed_${flag}.txt" 2>"${log_dir}/process_search_data_image_file_${flag}.log"

$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file="${data_dir}/audit_search_image_processed_${flag}.txt" --config_path="$index_config_path" --is_update_data=1 &>"${log_dir}/insert_data_to_search_index_${flag}.log"