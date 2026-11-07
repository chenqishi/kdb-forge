#!/bin/bash
# Copyright (c) 2023 Tencent.com, Inc. All Rights Reserved
# Authors: qishichen(qishichen@tencent.com)
# Date: 2024-12-04
export LC_ALL=C
 python data_parse_tools.py gen_query_form_chat_history_noat data/letain/all_message_letian_20241112_filter.txt >data/letain/query_noat_20241204.txt
 python difymodel_access.py test_one_model data/letain/query_noat_20241204_resnoprocess.txt  config/config_letian_online.json 1 2 1>data/letain/query_noat_result_20241204_res.txt 2>log/letian_nores.log &


python cross_broder_access/difymodel_access.py test_one_model \
    cross_broder_access/data/letain/query.txt \
    cross_broder_access/config/config_letian.json \
    --extra_input_params=cross_broder_access/config/extra_params_wayfair.json

cd /Users/chenqishi/stone_fish/knowledge_database_builder

python cross_broder_access/difymodel_access.py test_one_model \
    cross_broder_access/data/letain/query.txt \
    cross_broder_access/config/config_letian.json \
    --extra_input_params=cross_broder_access/config/extra_params_mercado.json
