#!/bin/bash
# Copyright (c) 2023 chenqishi, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2024-12-12

new_query_file=$1
platform=$2
dify_config_file=$3
index_config_path=$4
data_dir=$5
log_dir=$6
flag=$7

root_dir=./
PYTHON=python
all_has_processed_query_file=data/public/history_query.txt
all_query_file=$data_dir/all_query_${flag}.txt
need_process_query=$data_dir/need_process_query_${flag}.txt
cat $new_query_file > $all_query_file
platform_processed_query="${data_dir}/platform_processed_query_${flag}.txt"
# 检查历史文件是否为空
if [ ! -s "${all_has_processed_query_file}" ]; then
    echo "历史查询文件为空，所有查询将被视为新查询"
    cat "${all_query_file}" > "${need_process_query}"
else
    echo "处理平台 ${platform} 的查询"
    
    # 第一步：从历史文件中提取当前平台的查询到临时文件
    platform_processed_query="${data_dir}/platform_processed_query_${flag}.txt"
    awk -F"\t" -v platform="${platform}" '{if($1==platform) print $2}' "${all_has_processed_query_file}" > "${platform_processed_query}"
    
    echo "已从历史文件中提取平台查询，数量: $(wc -l < ${platform_processed_query})"
    
    # 第二步：比较新查询与历史查询，找出未处理的查询
    awk 'NR==FNR {seen[$1]=1; next} !seen[$1] {print $1}' "${platform_processed_query}" "${all_query_file}" > "${need_process_query}"
    
    echo "过滤后的新查询数量: $(wc -l < ${need_process_query})"
fi
index_name=$(echo $platform | tr '[:upper:]' '[:lower:]')


$PYTHON $root_dir/quality_tools/qa_quality_tools.py add_dify_quality_and_resplit_file \
    --qa_info_file=$data_dir/query_answer_${flag}.txt \
    --output_file=$data_dir/query_answer_add_quality_${flag}.txt \
    --dify_qa_filter=chatknowledge_qa_filter_for_chathistory \
     &>${log_dir}/run_batch_add_dify_quality_and_resplit_${flag}.log

$PYTHON $root_dir/commons/schema_trans.py trans_qa_to_search_data_one_file --qa_json_file=$data_dir/query_answer_add_quality_${flag}.txt  --output_file_handle=$data_dir/query_answer_add_quality_trans_search_data_${flag}.txt --platform=${platform}  --from_type="fixed_query_mining" &>$log_dir/trans_qa_to_search_data_one_file_${flag}.log     

#$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=$data_dir/query_answer_add_quality_trans_search_data_${flag}.txt   --config_path=$index_config_path  --is_only_title=true &>$log_dir/insert_fixquery_extract_qa_quality_batch_${flag}_search_data_to_search_index_${flag}.log
