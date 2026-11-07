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
from kdb.integrations.cross_border.dify_tools import DifyChatFlowRequest

class DifyModel(object):
    def __init__(self, api_base, api_key):
        self.api_base = api_base
        self.api_key = api_key
        self.remote_conversation_ids = {}
        self.dify_client = DifyChatFlowRequest(api_base=api_base, api_key=api_key)

    def query(self, conversation_id, query, **kwargs):
        remote_id = self.remote_conversation_ids.get(conversation_id, '')
        
        # 如果kwargs包含inputs参数，则传递给request_dify
        if 'inputs' in kwargs:
            response = self.dify_client.request_dify(query, remote_id, inputs=kwargs['inputs'])
        else:
            response = self.dify_client.request_dify(query, remote_id)
        
        if response and isinstance(response, dict):
            if 'conversation_id' in response:
                self.remote_conversation_ids[conversation_id] = response['conversation_id']
            return response.get('answer', '')
        elif isinstance(response, str):
            return response
        else:
            logging.error(f"query: {query} 无法获取有效响应")
            return "无法获取有效响应"

def output_workflow_vs_result(query_file, config_files):
    """
    处理查询文件并使用不同的Dify模型配置输出结果
    
    :param query_file: 包含查询的文件路径
    :param config_files: 模型配置文件的路径列表
    """
    models = []
    configs = []
    config_files = config_files.split(',')
    
    for config_file in config_files:
        with open(config_file, 'r') as f:
            config = json.load(f)
        if config['model'] == 'dify':
            models.append(DifyModel(config['base_url'], config['api_key']))
            configs.append(config)

    with open(query_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            parts = line.strip().split('\t')
            if len(parts) != 2:
                continue
            
            conversation_id, query = parts
            results = [conversation_id, query]
            
            for model, config in zip(models, configs):
                if config.get('query_prefix'):
                    new_query = config['query_prefix'] + query
                else:
                    new_query = query
                response = model.query(conversation_id, new_query)
                
                escaped_response = response.replace('\n', '\\n').replace('\r', '\\r')
                logging.info(f'model[{config["base_url"]}] query: {new_query} response: {response}')
                results.append(escaped_response)
            
            print('\t'.join(results))

def test_one_model(query_file, config_file, session_field=0, query_field=1, extra_input_params=None, is_fix=False):
    """
    测试单个Dify模型
    
    :param query_file: 查询文件路径
    :param config_file: 配置文件路径
    :param session_field: session字段索引
    :param query_field: query字段索引
    :param extra_input_params: 额外的input参数,可以是文件路径(str)或dict对象
    :param is_fix: 是否为修复模式,为True时仅重跑最后一列包含"无法获取有效响应"的行
    """
    with open(config_file, 'r') as f:
        config = json.load(f)    
    model = DifyModel(config['base_url'], config['api_key'])
    inputs = config.get('inputs', {})
    
    # 处理extra_input_params
    if extra_input_params is not None:
        if isinstance(extra_input_params, str):
            # 判断是否为文件路径
            if os.path.exists(extra_input_params):
                with open(extra_input_params, 'r', encoding='utf-8') as f:
                    extra_params = json.load(f)
            else:
                # 尝试解析为JSON字符串
                try:
                    extra_params = json.loads(extra_input_params)
                except json.JSONDecodeError:
                    logging.warning(f"extra_input_params既不是有效文件路径也不是有效JSON字符串: {extra_input_params}")
                    extra_params = {}
        elif isinstance(extra_input_params, dict):
            extra_params = extra_input_params
        else:
            logging.warning(f"extra_input_params类型不支持: {type(extra_input_params)}")
            extra_params = {}
        
        # 合并参数
        inputs.update(extra_params)
    
    with open(query_file, 'r', encoding='utf-8') as f_in:
        for line in f_in:
            line = line.strip("\n")
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            
            # 修复模式: 仅重跑最后一列包含"无法获取有效响应"的行
            if is_fix:
                if '无法获取有效响应' not in parts[-1]:
                    print(line)
                    continue
                # 去掉最后一列,重新跑结果替换
                line_without_last = '\t'.join(parts[:-1])
                conversation_id = parts[session_field]
                query = parts[query_field]
                if config.get('query_prefix'):
                    query = config['query_prefix'] + query
                if query.find('.png') != -1 or query.find('.jpg') != -1:
                    response = '图片无法处理'
                else:
                    response = model.query(conversation_id, query, inputs=inputs)
                    response = response.replace('\n', '\\n').replace('\r', '\\r')
                print(f'{line_without_last}\t{response}')
                continue
            
            conversation_id = parts[session_field]
            query = parts[query_field]
            if config.get('query_prefix'):
                query = config['query_prefix'] + query
            if query.find('.png') != -1 or query.find('.jpg') != -1:
                response = '图片无法处理'
            else:
                response = model.query(conversation_id, query, inputs=inputs)
                response = response.replace('\n', '\\n').replace('\r', '\\r')
            print(f'{line}\t{response}')

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
