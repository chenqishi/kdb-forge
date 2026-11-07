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
use_translated_field='ori_formatted_text'
PYTHON=python
##$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py run_batch_crawler --input_file=${input_file} --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_crawler_${flag}.log 
$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py crawl_batch_urls --input_file=${input_file} --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_crawler_${flag}.log 
$PYTHON $root_dir/knowledge_crawler_tool/web_crawl/web_batch_crawler.py process_crawled_content --crawler_url_info_file=${data_dir}/crawler_url_info_${flag}.txt --output_dir=${data_dir} --flag=${flag} &>${log_dir}/run_process_crawled_content_${flag}.log
$PYTHON $root_dir/knowledge_clear_tool/special_clear_method.py run_batch_clear_html_wordlist_and_payonner_data --data_file=${data_dir}/crawler_url_info_${flag}.txt  --html_file_field=4 1>${data_dir}/clear_all_qa_and_platform_article.txt 2>${log_dir}/run_clear_html_wordlist_and_payonner_data.log 
grep -v has_platform_article_result ${data_dir}/clear_all_qa_and_platform_article.txt >${data_dir}/clear_only_qa.txt
$PYTHON $root_dir/knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=${data_dir}/clear_only_qa.txt  --config_path=$index_config_path &>${log_dir}/insert_web_crawler_reclear_qa_${flag}_search_data_to_search_index_${flag}.log