#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-01
export LC_ALL=C
index_name=$1
es_config_file=$2
audit_result=$3
data_dir=$4
flag=$5
quality_level=$6
from_type=$7
audit_root=$(CDPATH= cd "$(dirname "$0")/../.." && pwd)
export PYTHONPATH="$audit_root/src:${PYTHONPATH:-}"

PYTHON=${KDB_PYTHON:-python} 
"$PYTHON" -m kdb.retrieval.application.search_index_data_interface gen_audit_data --index_name=$index_name --config_path=$es_config_file --audit_result=$audit_result --quality_level=$quality_level --from_type=$from_type 1>$data_dir/audit_data_${flag}.txt 
"$PYTHON" -m kdb.mining.transformations.schema_trans trans_es_data_to_excel --es_data_file=$data_dir/audit_data_${flag}.txt --output_file=$data_dir/audit_data_excel_${index_name}_${flag}.xlsx --headers=_id,title,content --is_need_trans_column=true

