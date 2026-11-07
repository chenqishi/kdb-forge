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
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH

PYTHON=python 
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py gen_audit_data --index_name=$index_name --config_path=$es_config_file --audit_result=$audit_result --quality_level=$quality_level --from_type=$from_type 1>$data_dir/audit_data_${flag}.txt 
$PYTHON $root_dir/commons/schema_trans.py trans_es_data_to_excel --es_data_file=$data_dir/audit_data_${flag}.txt --output_file=$data_dir/audit_data_excel_${index_name}_${flag}.xlsx 

