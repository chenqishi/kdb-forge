#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-11-16
export LC_ALL=C
index_config_path=config/config_for_search_index.json
python knowledge_clear_tool/excel_clear.py process_audit_excel data/sell_talker/C端销售助理-公司 销售QA库.xlsx   >data/sell_talker/cduan_qa_json.txt
##python knowledge_search_database/build_dataset_from_api_fastgpt.py build_dataset_from_local_json_file data/sell_talker/cduan_qa_onlyjson.txt $api_key $dataset_id $collection_id 1 0 >log/build_index.log
python knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index  --data_file=data/sell_talker/cduan_qa_onlyjson.txt --config_path=$index_config_path --use_platform_index=0 --index_name_assign=seller --data_type=qa &>log/insert_seller.log
awk -F"," '{print $1":"$2"\t\t"$1"\t"$1}' data/industry_special_knowledge/行业黑话.csv >data/industry_special_knowledge/trans.txt
python knowledge_search_database/build_dataset_from_api_fastgpt.py build_dataset_from_local_file data/industry_special_knowledge/trans.txt $api_key $dataset_id $collection_id 0 1 0 &>log/build_heihua_dataset.log

##python knowledge_search_database/build_dataset_from_api_fastgpt.py build_dataset_from_local_json_file data/mix_platfrom_crawler/all_qa_wordlist_and_pyonner.txt $api_key $dataset_id $collection_id 1 0 >log/build_index.log
python knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index  --data_file=data/mix_platfrom_crawler/all_qa_wordlist_and_pyonner.txt --config_path=$index_config_path --use_platform_index=0 --index_name_assign=mix --data_type=qa &>log/insert_mix_platform_crawler_data.log
python commons/excel_tools.py trans_qa_excel_to_json_with_tags ~/Documents/笔记本地/大模型项目鱼爷/乐天开发试验项目1/乐天_分层问题.xlsx data/letian/excel_clear/query_with_tags.json
python knowledge_interface_tools/search_index_data_interface.py test_insert_letian_excel  data/letian/excel_clear/query_with_tags.json   config/config_for_search_index.json &>log/test.insert.log.with_tags 
python knowledge_clear_tool/excel_clear.py process_audit_excel_mluti_query_forletin ~/Documents/笔记本地/大模型项目鱼爷/乐天开发试验项目1/乐天新增_同义query.xlsx data/letian/20241024/sheet_name_url_map.txt data/letian/excel_clear/synomous_query.xlsx 1>data/letian/excel_clear/synomous_query_json.txt
python knowledge_interface_tools/search_index_data_interface.py test_insert_letian_excel  data/letian/excel_clear/synomous_query_json.txt   config/config_for_search_index.json &>log/test.insert.log 
