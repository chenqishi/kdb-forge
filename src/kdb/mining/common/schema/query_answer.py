#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-08
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


import json

def convert_to_query_answer(input_file, query_file, output_file):
    # 读取输入文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取文本内容
    text = data['text']
    
    # 读取查询文件
    with open(query_file, 'r', encoding='utf-8') as f:
        queries = [line.strip() for line in f]
    
    # 使用正则表达式分割文本,保留分隔符
    segments = re.split(r'(。|：)', text)
    
    results = []
    current_query = None
    current_answer = []
    
    for segment in segments:
        if any(query in segment for query in queries):
            # 如果找到新的查询,保存前一个问答对(如果存在)
            if current_query:
                answer = ''.join(current_answer).strip().lstrip('：')
                results.append(f"{current_query}\t{answer}")
            
            # 开始新的问答对
            current_query = segment.strip()
            current_answer = []
        else:
            # 继续累积当前答案
            current_answer.append(segment)
    
    # 添加最后一个问答对
    if current_query:
        answer = ''.join(current_answer).strip().lstrip('：')
        results.append(f"{current_query}\t{answer}")
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(results))

# 使用示例


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()    