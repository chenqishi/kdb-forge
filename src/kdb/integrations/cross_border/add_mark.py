#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-21
"""
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
from dify_tools import DifyWorkFlowRequest

def add_mark_dify(data_file, dify_config, query_field):
    # 读取dify配置
    with open(dify_config, 'r') as f:
        config = json.load(f)
    
    # 初始化DifyWorkFlowRequest客户端
    dify_client = DifyWorkFlowRequest(
        api_base=config['base_url'],
        api_key=config['api_key']
    )
    
    # 读取数据文件并处理
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            parts = line.split('\t')
            if len(parts) <= query_field:
                logging.warning(f"行数据格式不正确，跳过: {line}")
                continue
                
            query = parts[query_field]
            if config.get('query_prefix'):
                query = config['query_prefix'] + query
                
            # 调用dify获取标记

            flag = dify_client.request_dify(query)
            if flag is None:
                flag = '请求失败'
            flag = flag.replace('\n', '\\n').replace('\r', '\\r')
                
            # 输出原始行数据加上标记
            print(f'{line}\t{flag}')


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()