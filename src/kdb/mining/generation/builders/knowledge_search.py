#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-08-23
description:该模块用于使用搜索方法收集问题的逻辑
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

import requests
from kdb.shared.config.legacy_config import GLOBAL_CONFIG

def send_post_request(query, api_key=_private_value('b3c0ac7618eb5f0a01c584d7')):
    url = f"{GLOBAL_CONFIG['dify_api_base']}/chat-messages"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        "inputs": {"query": query},
        "response_mode": "blocking",
        "user": "abc-123",
        "query": query
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # 将抛出HTTPError，如果响应状态不是200
        return json.loads(response.text)  # 返回JSON解析后的字典
    except:
        logging.error('err query[%s]', query)
        tb = traceback.format_exc()
        logging.error('err tb[%s]', tb)
        return None

def get_api_result(query):
    try:
        result_data = send_post_request(query)
        #outputs = result_data['data']['text']
        return result_data
    except Exception as e:
        logging.error('err result_data[%s]', result_data)
        raise e

def get_answer_for_question(question):
    result = get_api_result(question)
    # 假设API返回的结果中包含答案
    # 您可能需要根据实际API返回的结构调整这里
    return result.get('answer', '无')

def process_questions_file(file_path, platform_name):
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            question = line.strip()
            if question:
                if platform_name not in question:
                    query = platform_name + ' ' + question
                else:
                    query = question
                answer = get_answer_for_question(query)
                answer = answer.replace('\n', '。')
                print(f"{question}：{answer}")

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    questions_file = sys.argv[1]
    process_questions_file(questions_file, '法国乐天（Rakuten）')