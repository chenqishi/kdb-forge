#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-09-09
export LC_ALL=C
python knowledge_search_database/knowledge_process.py add_attrs_and_indexs data/letain/ 法国乐天 1>data/letain/final_qa_result_parse.txt
python knowledge_search_database/build_dataset_from_api_fastgpt.py build_dataset_from_local_file data/letian/final_qa_result_parse.txt $api_key $dataset_id $collection_id 1 10 0

api_base=http://120.77.147.247:5001/v1
. "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/private/runtime_config/shell/10724fe5aaffa52301c2.sh"
map_file=/Users/chenqishi/stone_fish/knowledge_database_builder/data/cdiscount_database/article_map_file.txt
answer_save_file=
python knowledge_clear_by_dify_model.py request $api_base $api_key $map_file $answer_save_file
python knowledge_clear_by_dify_model.py parse $answer_save_file $output_file
python knowledge_generate/knowledge_process.py process_data_cdiscount data/cdiscount_database/final_process_mini.txt >data/cdiscount_database/final_for_indexes_mini.txt


sh -x control_script/platform_knowledge_generate_from_raw_document.sh data/all_platform_clear/platform_raw_data_map.txt data/all_platform_clear log/all_platform_clear v1 $api_key $dataset_map_file &>log/all_platform_clear/run_batch_clear.log &
sh -x control_script/review_excel_qa_to_dataset.sh data/all_platform_clear/mid_quality_v1_review.xlsx data/all_platform_clear log/all_platform_clear v1 $api_key data/all_platform_clear/dataset_id_map.txt &>log/all_platform_clear/run_review_excel_qa_to_database.log &

sh -x control_script/platform_knowledge_generate_from_html.sh data/qutian/crawler/20241107/wait_crawler.txt  data/qutian/crawler/20241107 log v1 $api_key $dataset_map_file &>log/run_clear_html.log &

# chatknowledge generate


sh -x control_script/chatknowledge_process.sh data/chatknowledge/robot_remote_data_example.txt data/chatknowledge/chatbot_room_type_config.txt data/chatknowledge/chatbot_room_record.txt data/chatknowledge/chatbot_room_white.txt data/chatknowledge/20241114/ log/chatknowledge v1 $api_key $dataset_map_file data/chatknowledge/white_name_map.txt $filter_group_name &>log/run_chatknowledge.log &

python knowledge_clear_tool/excel_clear.py process_audit_image_excel_to_segment data/chatknowledge/20241223/qutian_chat_image_understanding2.xlsx data/qutian/image_clear/image_understanding.txt

sh -x control_script/analysis_chatbot_query.sh data/cross_broder_access/robot_remot_file.txt  data/cross_broder_access log/cross_broder_access cross_broder_access/config/config_query_mark.txt cross_broder_access/config/config_letian_new_v4.json v1 &>log/run_cross_letian_query_access.log &

python ../knowledge_database_builder/finsh_tmp/mp_article_parse.py parse_mp_article_info data/letian_article_tmp.txt >data/letian_article_tmp_parse.txt

sh -x control_script/gen_audit_data.sh mercado config/config_for_search_index.json 0,-1,1 data/meikeduo/wait_audit_data 20250301 &>log/tmp.log 

sh -x control_script/gen_audit_data_with_chathistory.sh mercado config/config_for_search_index.json -1,1 data/meikeduo/wait_audit_data 20250404 all all 120.77.147.247:/root/dify/dify-on-wechat/data/chat_message_forctk/all_message_meikeduo.txt  &>log/tmp.log 
sh -x control_script/fixed_query_knowledge_gen.sh data/meikeduo/query.txt Mercado config/config_dify_fixed_qa_answer.json config/config_for_search_index.json data/meikeduo/20250301 log/meikeduo v1  &>log/meikeduo/run_fixed_query.log
sh -x control_script/search_data_to_audit.sh  data/meikeduo/test_query.txt mercado    config/config_for_search_index.json  data/meikeduo/audit_data $des_file all all  &>log/gen_for_audit.log &

sh -x control_script/gen_audit_data.sh rufit config/config_for_search_index.json 1,0,-1 data/rufitself/ v1 all all

python control_service/off_task_control_service.py --script-dir ~/stone_fish/knowledge_database_builder/ &>log/run_off_task.log &
python data_control_tools/data_transfer_tools.py sql_database_transfer config/mysql_conn_config.json config/mysql_conn_config_japan.json data/trans_table.txt 1 &>log/transfer_sql_data.log &

python cross_broder_access/difymodel_access.py test_one_model \
    cross_broder_access/data/letain/query.txt \
    cross_broder_access/config/config_letian.json \
    --extra_input_params=cross_broder_access/config/extra_params_mercado.json

python cross_broder_access/dify_stress_test.py stress_test_dify \
    data/meikeduo/query.txt \
    cross_broder_access/config/config_mercado_stress.json \
    --max_workers=100 \
    --extra_input_params=cross_broder_access/config/extra_params_mercado_testpress.json  &>log/run_stress.log &

python cross_broder_access/dify_stress_test.py stress_test_dify \
    data/meikeduo/query.txt \
    cross_broder_access/config/config_mercado_stress.json \
    --max_workers=100 \
    --extra_input_params=cross_broder_access/config/extra_params_mercado_testpress_v220260419.json  &>log/run_stress_v2.log &
