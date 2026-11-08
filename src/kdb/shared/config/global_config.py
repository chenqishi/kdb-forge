from kdb.shared.config.loading import load_global_config
from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-13
"""
from kdb.shared.config.private_values import private_value as _private_value
import string
import sys
import os
import re
import json
import time
import math
import logging
import copy
import traceback
import codecs
from datetime import datetime
from datetime import timedelta

# 默认配置
_DEFAULT_CONFIG = {
    'fastgpt_api_base': 'http://120.77.147.247:4000',
    #'fastgpt_api_base': 'http://120.79.121.72:4000',
    'dify_api_base': 'http://120.77.147.247:5001/v1',
    'data_file_base_url': 'http://120.77.147.247:8001',
    'dify_api_key_forward_nomix': _private_value('187f68ca2839812b58e86173'), # forward:转发群,不区分发送对象， normal:普通群,分发送对象, mix:多平台混合，需要进行平台识别, nomix:单平台，不需要平台识别
    'dify_api_key_forward_mix': _private_value('fc663c5f3e01ae3330a55a17'),
    'dify_api_key_normal_nomix': _private_value('3f10680fdb2f81470c8262ed'),
    'dify_api_key_normal_mix': _private_value('f0de64e4fcda6a5459f0383c'),
    'dify_api_key_chatknowledge_qa_filter': _private_value('6e14e82b8f59134adc0050dc'),
    'dify_api_key_chatknowledge_qa_filter_for_chathistory': _private_value('22b906ed275266cd2d9610f5'),
    'dify_api_key_mluti_vision_forward_nomix': _private_value('3f91111694ad31939c4e4706'),
    'dify_api_key_mluti_vision_forward_mix': _private_value('1252001b34191398d595d533'),
    'dify_api_key_payoneer_clear': _private_value('a1f9431c838d98377cb814fb'),
    'dify_api_key_mluti_vision_normal_nomix': _private_value('fc3611094cec33e2d3e73c81'),
    'dify_api_key_mluti_vision_normal_mix': _private_value('67290e3ee3379ead8a4f22cd'),
    'chat_qa_mining_task_control_global_black_nick_name': '🫙路飞跨境军团|单侧群（5）|路飞智能_全员|👩🏻‍💼Monica智能业务突进🔥|单侧- 群|石|杨若愚_Luke|小助理|Lea_RakutenFR|RuFitAi智能业务ARR100|路飞智能-美客多 AI招商顾问|Justin_美客多|P卡-路飞智能|DEMO|SM Premium会员接待室',
    'app_config_get_url': 'https://www.lufitglobalselling.com:8888/api/rufit-ai/intranet/ai/config/getRoleConfigList?appId={app_id}&client={client}',
    'dify_api_key_segment': _private_value('695bba4a365d54bbe7925d78'),
    'dify_api_key_subtract': _private_value('a2dd9333ddb081d7ab7d05ef'),
    'dify_api_key_qa_filter': _private_value('21d793fc99dba18b78d59297'),
    'tmp_file_dir': 'data/tmp_dir'
}

# 尝试从外部配置文件加载配置
def _load_global_config():
    """Load this project configuration with its unchanged defaults."""
    return load_global_config(_DEFAULT_CONFIG, _PROJECT_ROOT)

# 初始化全局配置
GLOBAL_CONFIG = _load_global_config()


