#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
#root_dir=$(cd $(dirname $0); pwd)
query_file=$1
index_name=$2
es_config_file=$3

data_dir=$4
des_file=$5
quality_level=$6
from_type=$7
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH

audit_result=1,-1
quality_level=high,mid
PYTHON=python 
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py search_for_audit_data  --index_name=$index_name --config_path=$es_config_file \
    --audit_result=$audit_result \
    --quality_level=$quality_level \
    --query_file=$query_file \
    --from_type=$from_type 1>$data_dir/search_audit_data_mid.txt 

headers='_id,search_query,title,content,synonyms_title,supply_info_query,platform,data_type,from_type,audit_result,quality_level'
$PYTHON $root_dir/commons/schema_trans.py trans_es_data_to_excel --es_data_file=$data_dir/search_audit_data_mid.txt --headers=$headers --output_file=$des_file

