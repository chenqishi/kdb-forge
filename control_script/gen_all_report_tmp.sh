#!/bin/bash
# Copyright (c) 2024 chenqishi2019@gmail.com, Inc. All Rights Reserved
# Authors: qishichen(chenqishi2019@gmail.com)
# Date: 2025-02-23
export LC_ALL=C
start_time=$1
end_time=$2
flag=$3


python static_report/robot_answer_static.py static_norm_query_report  data/robot_report/20250222/parse_wx_merge_${flag}_result_readd_norm.txt data/robot_report/20250222/parse_wx_merge_${flag}_result_readd_norm_stat_result.txt
awk -F "\t" '{print $2"\t"$3"\t"$4"\t"$11"\t"$12"\t"$NF}' data/robot_report/20250222/parse_wx_merge_${flag}_result_readd_norm.txt >data/robot_report/20250222/parse_wx_merge_${flag}_result_readd_norm_show.txt



exit 



 python cross_broder_access/data_parse_tools.py gen_query_and_answer_form_chat_history data/robot_report/all_message_letian_20241112.txt data/robot_report/black_group_file_letian.txt $start_time $end_time 1>data/robot_report/20250222/parse_wx_1month.txt  2>log/static_letian.log
grep -v at_and_nogroup data/robot_report/20250222/parse_wx_1month.txt >data/robot_report/20250222/parse_wx_noat_1month.txt
grep at_and_nogroup data/robot_report/20250222/parse_wx_1year.txt >data/robot_report/20250222/parse_wx_onlyat_1month.txt
python cross_broder_access/difymodel_access.py test_one_model data/robot_report/20250222/parse_wx_noat_1month.txt cross_broder_access/config/config_letian_online.json  4 9 1>data/robot_report/20250222/parse_wx_noat_1month_result.txt 2>log/access_letian_robotic.log &
awk -F"\t" '{print $1"\t"$2"\t"$3"\t"$4"\t"$5"\t"$6"\t"$7"\t"$8"\t"$9"\t"$10"\t"$11"\t"$13}' data/robot_report/20250222/parse_wx_noat_1month_result.txt  >data/robot_report/20250222/parse_wx_noat_1month_result_readd.txt
cat data/robot_report/20250222/parse_wx_noat_1month_result_readd.txt data/robot_report/20250222/parse_wx_onlyat_1month.txt >data/robot_report/20250222/parse_wx_merge_1month_result_readd.txt
python -u cross_broder_access/query_norm_anslysis.py norm_query_file data/robot_report/20250222/parse_wx_merge_1month_result_readd.txt data/robot_report/20250222/parse_wx_merge_1month_result_readd_norm.txt config/config_ali_embedding.json 9 &>log/query_norm_wx_1month.log &
python static_report/robot_answer_static.py static_norm_query_report  data/robot_report/20250222/parse_wx_merge_1month_result_readd_norm.txt data/robot_report/20250222/parse_wx_merge_1month_result_readd_norm_stat_result.txt
awk -F "\t" '{print $2"\t"$3"\t"$10"\t"$11"\t"$NF}' data/robot_report/20250222/parse_wx_merge_1month_result_readd_norm.txt >data/robot_report/20250222/parse_wx_merge_1month_result_readd_norm_show.txt




python cross_broder_access/data_parse_tools.py gen_query_and_answer_form_chat_history data/robot_report/all_message_mp_letian.txt data/robot_report/black_group_file_letian.txt $start_time $end_time 1>data/robot_report/20250222/parse_mp_1month_letian.txt 2>log/static_letian_mp.log

python -u cross_broder_access/query_norm_anslysis.py norm_query_file data/robot_report/20250222/parse_mp_1month_letian.txt data/robot_report/20250222/parse_mp_1month_letian_norm_query.txt config/config_ali_embedding.json 9 &>log/query_norm.log 
python static_report/robot_answer_static.py static_norm_query_report data/robot_report/20250222/parse_mp_1month_letian_norm_query.txt data/robot_report/20250222/parse_mp_1month_letian_norm_query_stat_result.txt
awk -F "\t" '{print $1"\t"$2"\t"$11"\t"$12"\t"$NF}' /Users/chenqishi/stone_fish/knowledge_database_builder/data/robot_report/20250222/parse_mp_1month_letian_norm_query.txt >data/robot_report/20250222/parse_mp_1month_letian_detail_show.txt

