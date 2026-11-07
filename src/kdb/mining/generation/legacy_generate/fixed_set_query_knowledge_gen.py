#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-15
"""
import sys
import os
import json
import logging
import traceback
from commons.dify_tools import DifyWorkFlowRequest

def get_query_answer(query_file, config_file,  platform, query_field=0, index_name=''):
    """
    测试单个Dify模型
    """
    with open(config_file, 'r') as f:
        config = json.load(f)    
    logging.info(f"dify config: {config}")
    model = DifyWorkFlowRequest(config['base_url'], config['api_key'])
    if not index_name:
        index_name = platform

    other_inputs = {
        'platform': platform,
        'index_name': index_name,
    }
    
    with open(query_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            line = line.strip()
            parts = line.split('\t')
            if len(parts) < 1:
                continue
            query = parts[query_field]
            answer = model.request_dify(query, other_inputs=other_inputs)
            qa_info = dict()
            qa_info = {}
            qa_info['q'] = query
            qa_info['a'] = answer
            qa_info['platform'] = platform            
            print(json.dumps(qa_info, ensure_ascii=False))

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
