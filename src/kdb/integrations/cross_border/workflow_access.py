#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-15
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

import requests
import json

class OpenAiModel(object):
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.conversations = {}

    def chat_completion(self, messages, conversation_id=None, **kwargs):
        if conversation_id:
            if conversation_id not in self.conversations:
                self.conversations[conversation_id] = []
            self.conversations[conversation_id].extend(messages)
            messages = self.conversations[conversation_id]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "messages": messages,
            **kwargs
        }

        response = requests.post(f"{self.base_url}/v1/chat/completions", 
                                 headers=headers, 
                                 data=json.dumps(data))
        
        return response.json()

    def query(self, conversation_id, query, **kwargs):
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        self.conversations[conversation_id].append({"role": "user", "content": query})
        
        response = self.chat_completion(self.conversations[conversation_id], conversation_id, **kwargs)
        
        if 'choices' in response and len(response['choices']) > 0:
            assistant_message = response['choices'][0]['message']
            self.conversations[conversation_id].append(assistant_message)
            return assistant_message['content']
        else:
            logging.error(f"query: {query} 无法获取有效响应: {response}")
            return "无法获取有效响应"


# 使用示例
# llm = LargeLanguageModel("https://api.example.com", "your-api-key")
# response = llm.chat_completion([{"role": "user", "content": "你好"}], conversation_id="123")
# print(response)

def output_workflow_vs_result(query_file, config_files):
    """
    处理查询文件并使用不同的模型配置输出结果
    
    :param query_file: 包含查询的文件路径
    :param config_files: 模型配置文件的路径列表
    """
    # 读取并初始化模型
    models = []
    configs = []
    config_files = config_files.split(',')
    for config_file in config_files:
        with open(config_file, 'r') as f:
            config = json.load(f)
        if config['model'] == 'openai':
            models.append(OpenAiModel(config['base_url'], config['api_key']))
            configs.append(config)
    # 处理查询文件并输出结果
    with open(query_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            parts = line.strip().split('\t')
            if len(parts) != 2:
                continue  # 跳过格式不正确的行
            
            conversation_id, query = parts
            results = [conversation_id, query]
            
            for model, config in zip(models, configs):
                if config.get('query_prefix'):
                    new_query = config['query_prefix'] + query
                else:
                    new_query = query
                response = model.query(conversation_id, new_query)
                # 处理回复中的换行符
                escaped_response = response.replace('\n', '\\n').replace('\r', '\\r')
                results.append(escaped_response)
            
            print('\t'.join(results))

def test_one_model(query_file, config_file):
    """
    """
    with open(config_file, 'r') as f:
        config = json.load(f)    
    model = OpenAiModel(config['base_url'], config['api_key'])
    with open(query_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            parts = line.strip().split('\t')
            if len(parts) != 2:
                continue  # 跳过格式不正确的行
            conversation_id, query = parts
            if config.get('query_prefix'):
                query = config['query_prefix'] + query
            
            response = model.query(conversation_id, query)
            print(conversation_id, query, response)

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()    