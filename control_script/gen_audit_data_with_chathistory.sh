#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
#root_dir=$(cd $(dirname $0); pwd)
index_name=$1
es_config_file=$2
audit_result=$3
data_dir=$4
flag=$5
quality_level=$6
from_type=$7
remote_chathistory_file=$8
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH

PYTHON=python 
$PYTHON $root_dir/data_control_tools/remote_machine_tools.py download_file_from_remote_machine \
    --remote_file_path=$remote_chathistory_file \
    --local_file_path=$data_dir/all_message_${index_name}.txt \
    --username=root \
    --password="$(cat "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/36da5de6dcbd8cb09691.value")" \
    --port=22
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py gen_audit_data --index_name=$index_name --config_path=$es_config_file --audit_result=$audit_result --quality_level=$quality_level --from_type=$from_type 1>$data_dir/audit_data_${flag}.txt 
$PYTHON $root_dir/chatknowledge/match_chat_history_to_chathistory.py process_qa_file --data_file=$data_dir/audit_data_${flag}.txt  --chat_history_file=$data_dir/all_message_${index_name}.txt 1>$data_dir/audit_dat_with_history_${flag}.txt
$PYTHON $root_dir/commons/schema_trans.py trans_es_data_to_excel --es_data_file=$data_dir/audit_dat_with_history_${flag}.txt --output_file=$data_dir/audit_data_excel_${index_name}_${flag}.xlsx 

