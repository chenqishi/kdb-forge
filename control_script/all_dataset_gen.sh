#!/bin/bash
# Copyright (c) 2023 qishichen, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-01-04
export LC_ALL=C
root_dir=./
export PYTHONPATH=$root_dir:$PYTHONPATH
#乐天 1）excel知识 [done] 2）chat审核 3）segment知识[done]
#趣天 1) 文档[done] 2）图片知识 3)html faq[done]
#全的：1）wordfirst开店知识[done] 2）esg 40000[done] 3)所有文档[done]
#onbuy: 1)文档
#cdiscount: 1)文档[done] 2)html 
#yiwu: 1)html [done]
#美客多 1）文档
sh -x control_script/build_dataset_once_tmp.sh  &>log/all_dataset_gen.log

sh -x control_script/platform_knowledge_generate_from_raw_document_tmp_letaian.sh  &>log/letaian_dataset_gen.log 

sh -x control_script/platform_knowledge_generate_from_raw_document_tmp.sh data/all_platform_clear/platform_raw_data_map.txt data/all_platform_clear log/all_platform_clear v1  test config/config_for_search_index.json  &>log/all_platform_clear/run_batch_clear.log &

sh -x control_script/platform_knowledge_generate_from_html_tmp.sh data/qutian/crawler/20241107/wait_crawler.txt  data/qutian/crawler/20241107 log v1 test test config/config_for_search_index.json &>log/run_clear_html.log &

python knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index --data_file=data/esg_all/parse_qa_info.txt --config_path=config/config_for_search_index.json --platform=unkown --from_type=esg --data_type=doc --use_platform_index=False --index_name_assign=mix &>log/insert_esg_all_to_search_index.log


sh -x control_script/platform_knowledge_generate_from_html_tmp.sh data/japanpassport/20250119/wait_crawler.txt data/japanpassport/20250119 log/japanpassport v1 test test config/config_for_search_index.json &>log/run_clear_html.log &

sh -x control_script/platform_knowledge_generate_from_raw_document_tmp.sh   data/meikeduo/platform_raw_data_map.txt  data/meikeduo/20250123 log/meikeduo v1 test  config/config_for_search_index.json &>log/run_batch_clear.log &
sh -x control_script/insert_audit_excel.sh ~/Documents/笔记本地/大模型项目鱼爷/美客多资料/数据审核QAv1.xlsx data/meikeduo/audit_data config/config_for_search_index.json v1 &>log/trans_to_insert.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/乐天开发试验项目1/数据审核QA文本20250208.xlsx
 sh -x control_script/insert_audit_excel.sh $data_file data/letian/audit_data config/config_for_search_index.json v1 &>log/trans_to_insert.log &
 sh -x control_script/platform_knowledge_generate_from_html.sh data/leelinesourcing/wait_crawler.txt data/leelinesourcing/20250212 log/leelinesourcing v1 test test config/config_for_search_index.json &>log/run_clear_html.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/美客多资料/数据审核QAv1_add.xlsx
 sh -x control_script/insert_audit_excel.sh $data_file data/letian/audit_data config/config_for_search_index.json v1 &>log/trans_to_insert.log &
 data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/美客多资料/数据审核QAv1.xlsx
 sh -x control_script/insert_audit_excel.sh $data_file data/letian/audit_data config/config_for_search_index.json v1 &>log/trans_to_insert.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/美客多资料/数据审核QAv2.xlsx
sh -x control_script/insert_audit_excel_image.sh  $data_file data/meikeduo/audit_data  config/config_for_search_index.json v2 &>log/trans_to_insert.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/乐天开发试验项目1/数据审核QA文本20250220.xlsx
sh -x control_script/insert_audit_excel_image.sh  $data_file data/letian/audit_data/   config/config_for_search_index.json v2 &>log/trans_to_insert.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/深跨协/数据审核QA0307.xlsx
data_file=~/Documents/笔记本地/大模型项目鱼爷/深跨协/数据审核QA0324_luke.xlsx
sh -x control_script/insert_audit_excel_image.sh  $data_file data/shenkuaxie/audit_data/   config/config_for_search_index.json v2 &>log/trans_to_insert.log &
sh -x control_script/chatknowledge_process.sh data/chatknowledge/robot_remote_data_example.txt data/chatknowledge/chatbot_room_type_config.txt data/chatknowledge/chatbot_room_record.txt data/chatknowledge/chatbot_room_white.txt data/chatknowledge/20250301 log/chatknowledge all_es_v1 data/chatknowledge/white_name_map.txt all config/config_for_search_index.json &>log/run_chatknowledge.log &

sh -x control_script/platform_knowledge_generate_from_html.sh data/caguuu/wait_crawler.txt data/caguuu/20250308 log/caguuu v1 test test  config/config_for_search_index.json &>log/run_clear_html.log &
sh -x control_script/platform_knowledge_generate_from_html.sh data/smartdetax/wait_crawler.txt  data/smartdetax/20250403 log/smartdetax v1  test test  config/config_for_search_index.json &>log/run_clear_html.log &
data_file=/Users/chenqishi/Documents/笔记本地/大模型项目鱼爷/smartdetax/数据审核QA文本_20250101.xlsx
sh -x control_script/insert_audit_excel_image.sh  $data_file data/smartdetax/audit_data/   config/config_for_search_index.json v2 &>log/trans_to_insert.log &
