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
from kdb.shared.config.global_config import GLOBAL_CONFIG

def send_post_request(target_url, api_key=_private_value('f4f230b268c678437a093c36')):
    url = f"{GLOBAL_CONFIG['dify_api_base']}/workflows/run"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        "inputs": {"input_url": target_url},
        "response_mode": "blocking",
        "user": "abc-123"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # 将抛出HTTPError，如果响应状态不是200
        return json.loads(response.text)  # 返回JSON解析后的字典
    except requests.exceptions.HTTPError as errh:
        print(f"Http Error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"OOps: Something Else: {err}")

def get_api_result(target_url):
    try:
        result_data = send_post_request(target_url)
        outputs = result_data['data']['outputs']
    
        return outputs
    except Exception as e:
        logging.error('err result_data[%s]', result_data)
        raise e
    


def crawler_to_file(target_url, save_file):
    """
    将target_url的网页内容保存到save_file
    """
    try:
        result_data = send_post_request(target_url)
    
        try:
            outputs = result_data['data']['outputs']
        except:
            logging.error('err result_data[%s]', result_data)
        outputs = result_data['data']['outputs']
        output_str = json.dumps(outputs, ensure_ascii=False)
        with open(save_file, 'w', encoding='utf-8') as f:
            f.write(output_str)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('err tb[%s]', tb)
        print("crawler_to_file error:", e)

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    target_url = sys.argv[1]
    save_file = sys.argv[2]
    crawler_to_file(target_url, save_file)  
