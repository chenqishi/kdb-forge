#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-07
export LC_ALL=C

root_dir=./
input_file=$1
data_dir=$2
log_dir=$3
flag=$4
api_key=$5
dataset_map_file=$6
index_config_path=$7
export PYTHONPATH=$root_dir:$PYTHONPATH
need_translated=0
use_translated_field='formatted_text'
PYTHON=python
##$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py run_batch_crawler --input_file=${input_file} --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_crawler_${flag}.log 
$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py crawl_batch_urls --input_file=${input_file} --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_crawler_${flag}.log 
$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py process_crawled_content --crawler_url_info_file=${data_dir}/crawler_url_info_${flag}.txt --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_process_crawled_content_${flag}.log

if [ $need_translated -eq 1 ]; then
    $PYTHON $root_dir/knowledge_clear_tool/knowledge_translate_by_dify.py run_batch_translate_html_json_content --input_file=${data_dir}/crawler_and_process_results_${flag}.txt  --output_file=${data_dir}/web_crawler_translated_${flag}.txt --field_num=-1  &>${log_dir}/run_batch_translate_html_json_content_${flag}.log
else
    cp ${data_dir}/crawler_and_process_results_${flag}.txt ${data_dir}/web_crawler_translated_${flag}.txt
fi

# 生成qa知识
$PYTHON $root_dir/knowledge_clear_tool/knowledge_html_clear_by_dify.py run_batch_clear_html_content --input_file=${data_dir}/web_crawler_translated_${flag}.txt \
    --output_file=${data_dir}/web_crawler_clear_qa_${flag}.txt --process_field_num=-1 \
    --process_field=${use_translated_field}   &>${log_dir}/run_batch_clear_html_json_content_${flag}.log
$PYTHON $root_dir/quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info --input_file=${data_dir}/web_crawler_clear_qa_${flag}.txt --output_file=${data_dir}/web_crawler_reclear_qa_${flag}.txt --process_field_num=-1 &>${log_dir}/run_batch_re_clear_qa_info_${flag}.log

#schema处理成 es 插入格式 ${data_dir}/web_crawler_reclear_qa_${flag}.txt
$PYTHON $root_dir/commons/schema_trans.py batch_trans_qa_to_search_data --batch_file=${data_dir}/web_crawler_reclear_qa_${flag}.txt --output_file=${data_dir}/web_crawler_reclear_qa_${flag}_search_data.txt --field_num=-1 --platform_field_num=0 &>${log_dir}/web_crawler_reclear_qa_${flag}_search_data.log
#插入到es中
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=${data_dir}/web_crawler_reclear_qa_${flag}_search_data.txt --config_path=$index_config_path &>${log_dir}/insert_web_crawler_reclear_qa_${flag}_search_data_to_search_index_${flag}.log

exit 0
$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_split_json_quality_to_excel \
    --batch_file=${data_dir}/web_crawler_reclear_qa_${flag}.txt \
    --platform_field_num=0 \
    --high_quality_excel_file=$data_dir/high_quality_${flag}.xlsx \
    --mid_quality_excel_file=$data_dir/mid_quality_${flag}.xlsx \
    --low_quality_excel_file=$data_dir/low_quality_${flag}.xlsx \
    --field_num=8 2>$log_dir/batch_split_json_quality_to_excel_${flag}.log

$PYTHON $root_dir/knowledge_clear_tool/tools/schema_trans.py batch_select_high_quality_qa_to_json \
    --batch_file=${data_dir}/web_crawler_reclear_qa_${flag}.txt \
    --platform_field_num=0 \
    --field_num=8 1>$data_dir/high_quality_for_qa_onlyjson_${flag}.txt 2>$log_dir/batch_select_high_quality_qa_to_json_${flag}.log
#$PYTHON $root_dir/knowledge_search_database/fastgpt_dataset_build.py batch_add_qa_dataset $data_dir/high_quality_for_qa_onlyjson_${flag}.txt ${dataset_map_file} ${api_key} 0 &>$log_dir/batch_add_segment_qa_dataset_${flag}.log
