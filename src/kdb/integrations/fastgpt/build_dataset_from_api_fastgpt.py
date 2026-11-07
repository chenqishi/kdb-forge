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
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('knowledge_search_database/build_dataset_from_api_fastgpt.py')
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
import pandas as pd
# 添加父目录到Python搜索路径
current_dir = os.path.dirname(os.path.abspath(__legacy_source_file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)#from concurrent.futures import ThreadPoolExecutor
from knowledge_generate.knowledge_index_builder import get_fastgpt_index
import requests
from commons.common_utils import load_map_file
from config_tools import config
#URL_BASE = "https://api.fastgpt.in"
URL_BASE = config.GLOBAL_CONFIG.get("fastgpt_api_base")
#URL_BASE = "http://120.79.121.72:4000"

def build_dataset(name, api_key=_private_value('e2ccea9644441a4e7d46facc')):
    """
    使用新的 API 接口创建数据集
    """
    url = f"{URL_BASE}/api/core/dataset/create"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "parentId": None,
        "type": "dataset",
        "name": name,
        "intro": "通过 API 创建的数据集",
        "avatar": "",
        "vectorModel": "text-embedding-ada-002",
        "agentModel": "gpt-3.5-turbo-16k"
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        return None
    response_json = response.json()
    return response_json



def build_documents(name, dataset_id, api_key=_private_value('b86338254144f66b661c2d6d'), metadata=None):
    url = f"{URL_BASE}/api/core/dataset/collection/create"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "datasetId": dataset_id,
        "parentId": None,
        "name": name,
        "type": "virtual",
        "metadata": metadata or {}
    }
    logging.info(f'build_documents request: {data}')
    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        return None

    logging.info(f'build_documents: {response.json()}')
    return response.json()



def add_segment(collection_id, api_key, data, training_mode="chunk", prompt=None, bill_id=None):
    url = f"{URL_BASE}/api/core/dataset/data/pushData"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "collectionId": collection_id,
        "trainingMode": training_mode,
        "data": []
    }

    for item in data:
        data_item = {"q": item["q"]}
        if "a" in item:
            data_item["a"] = item["a"]
        if "indexes" in item:
            data_item["indexes"] = [{"text": index} for index in item["indexes"]]
        payload["data"].append(data_item)

    if prompt:
        payload["prompt"] = prompt
    if bill_id:
        payload["billId"] = bill_id

    logging.debug('add_segment: %s %s', headers, payload)
    response = requests.post(url, headers=headers, json=payload)
    logging.debug('url[%s], response: %s', url, response.text)
    
    if response.status_code != 200:
        return None
    try:
        data_json = response.json()
        if data_json["code"] == 200:
            return data_json
    except:
        logging.error('add segment error segment: %s', data)
        return None


def add_one_segment_and_add_indexes(dataset_id, document_id, api_key, query, answer, plat_form=None, synonym_querys=None, tag_infos=None, traing_mode='chunk'):
    """
    """
    indexes = get_fastgpt_index(query, answer, plat_form)

    if synonym_querys:
        merge_query = f'{query}|"相同问题:"{";".join(synonym_querys)}'
        content = f'{merge_query}\n{answer}'
        indexes.append(''.join(synonym_querys))
    else:
        content = f'{query}\n{answer}'
    
    data = {"q": content, "indexes": indexes}
    attrs = dict()
    
    if plat_form:
        attrs['platform'] = plat_form
    if tag_infos:
        attrs['tags'] = tag_infos
    if attrs:
        data['a'] =json.dumps(attrs, ensure_ascii=False)
    is_success = False
    for try_index in range(3):
        add_info = add_segment(collection_id=document_id, api_key=api_key, data=[data], training_mode=traing_mode)
        if add_info:
             logging.debug("add_segment: %s %s", document_id, add_info)
             is_success = True
             break
        else:
            logging.error('add_segment error: %s %s %s', try_index, document_id, add_info)
    return is_success
            

def parse_segment(text, use_keywords=True):
    # 提取正文内容

    # 提取关键词
    keyword_match = re.search(r'-.*?关键词：(.*?)\n', text)
    keywords = keyword_match.group(1).strip() if keyword_match else None

    # 提取图谱标签
    label_match = re.search(r'-.*?图谱标签: (.*?)\n', text)
    label = label_match.group(1).strip() if label_match else None

    # 提取属性
    attribute_match = re.search(r'-.*?属性：(.*?)$', text)
    attribute = attribute_match.group(1).strip() if attribute_match else None
    content = re.sub(r'-.*?关键词：.*?\n', '', text)
    content = re.sub(r'-.*?图谱标签: .*?\n', '', content)
    content = re.sub(r'-.*?属性：.*?$', '', content)
    keywords = re.split(r'、|,|\ ', keywords) if keywords else []
    if use_keywords:
        return {
            'content': content,
            'keywords': keywords,
            'label': label,
            'attribute': attribute
        }
    else:
        return {
            'content': content,
            'label': label,
            'attribute': attribute
        }

def build_dataset_from_local_file(local_file_path, api_key='fastgpt-zobup1z6WAgex08nE4gs5S94v8XbUuWtui8gudNt4MIXDvnQkLkxGXU', dataset_id=None, document_id=None, 
                                  qa=1, batch_size=1, start_index=0):
    """
    从本地文件构建数据集,每行的格式为title\tcontent\tattribute\tindexes（以|分割）
    """
    file_name = os.path.splitext(os.path.basename(local_file_path))[0]
    
    if dataset_id is None or dataset_id == "NULL":
        dataset_info = build_dataset(file_name + '_api_build')
        dataset_id = dataset_info["id"]
    if document_id is None or document_id == "NULL":
        document_info = build_documents("init no value", dataset_id)
        document_id = document_info['document']["id"]
    
    qa = bool(qa)
    index = 0
    data = []
    logging.info(f'api_base: {URL_BASE}')
    with open(local_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            index += 1
            if index < start_index:
                continue
            print(f'处理第 {index} 行')
            
            title, content, attribute, indexes = line.strip().split('\t')
            q = f"{title}\n{content}"
            a = attribute
            indexes = indexes.split('|') if indexes else []
            
            item = {"q": q, "indexes": indexes}
            if qa:
                item["a"] = a
            
            data.append(item)
            
            if len(data) >= batch_size:  # 每100条数据批量添加一次
                add_info = add_segment(collection_id=document_id, api_key=api_key, data=data)
                logging.debug("add_segment: %s %s", document_id, add_info)
                data = []
    
    if data:  # 添加剩余的数据
        add_info = add_segment(collection_id=document_id, api_key=api_key, data=data)
        logging.debug("添加片段: %s %s", document_id, add_info)
    return index

def add_one_segment(document_id, api_key, content, keywords=None, answer=None):
    one_data = {'q': content}
    if keywords:
        one_data['indexes'] = [','.join(keywords)]

    return add_segment(document_id, api_key, data=[one_data], training_mode="chunk")

def build_dataset_from_local_json_file(local_file_path, api_key=_private_value('96363e33b63b99e8d1d39178'), 
                                       dataset_id=None, document_id=None, qa=1, start_inndex=0):
    """
    """
    file_name = local_file_path.split("/")[-1]
    file_name, file_extension = os.path.splitext(file_name)
    #segmets = open(local_file_path, "r").read().split("\n------\n")
    if dataset_id is None or dataset_id=="NULL":
        dataset_info = build_dataset(file_name + '_api_build')
        dataset_id = dataset_info["id"]
    if document_id is None or document_id=="NULL":
        document_info = build_documents("init no value", dataset_id)
        document_id = document_info['document']["id"]
    qa = bool(qa)
    index = 0 
    with open(local_file_path, 'r') as f:
        for line in f:
            index += 1
            if index < start_inndex:
                continue
            print('prcess_index: {}'.format(index))
            fields = line.strip().split('\t')
            parse_segment_info = json.loads(fields[-1])
            if 'platform' in parse_segment_info:
                platform = parse_segment_info['platform']
            else:
                platform = None
            if platform and platform.find('mix') != -1:
                platform = None
            if not qa:
                content = parse_segment_info['title'] + parse_segment_info['content']
            #keywords = parse_segmen  xt_info['keywords'] + [parse_segment_info['label']] #+ [parse_segment_info['attribute']]
                add_info = add_one_segment(document_id, api_key=api_key, content=content)
            else:
                add_info = add_one_segment_and_add_indexes(dataset_id, document_id, api_key=api_key, query=parse_segment_info['title'], 
                                                           answer=parse_segment_info['content'], 
                                                           plat_form=platform, 
                                                           synonym_querys=parse_segment_info.get('synonyms_query'), 
                                                           tag_infos=parse_segment_info.get('tag_infos'), traing_mode='chunk')
            logging.debug("add_segment: %s %s", document_id, add_info)
    return index


def build_dataset_from_api_fastgpt_excel(excel_file_path, api_key='fastgpt-zobup1z6WAgex08nE4gs5S94v8XbUuWtui8gudNt4MIXDvnQkLkxGXU', 
                                         dataset_id=None, document_id=None, 
                                         qa=1, batch_size=1, start_index=0, sheet_num=0, plat_form=None):
    """
    从Excel文件构建数据集,第一列为q,第二列为a
    """
    file_name = os.path.splitext(os.path.basename(excel_file_path))[0]
    
    if dataset_id is None or dataset_id == "NULL":
        dataset_info = build_dataset(file_name + '_api_build')
        dataset_id = dataset_info["id"]
    if document_id is None or document_id == "NULL":
        document_info = build_documents("init no value", dataset_id)
        document_id = document_info['document']["id"]
    
    qa = bool(qa)
    index = 0
    data = []
    
    # 读取Excel文件
    df = pd.read_excel(excel_file_path, sheet_name=sheet_num)
    
    def is_valid_string(s):
        return bool(re.search(r'[\u4e00-\u9fff\w]', str(s)))
    
    for _, row in df.iterrows():
        index += 1
        if index < start_index:
            continue
        print(f'处理第 {index} 行')
        
        q = row.iloc[0]
        a = row.iloc[1]
        
        # 如果q或a缺失,或者不包含有效字符,跳过该行
        if pd.isna(q) or pd.isna(a) or not is_valid_string(q) or not is_valid_string(a):
            continue
        add_one_segment_and_add_indexes(dataset_id, document_id, api_key, q, a, plat_form)    
    return index


class DatasetBuilder(object):
    def __init__(self, api_key=_private_value('28e24c9e1ec4e132fbdb82aa'), dataset_id=None, document_id=None):
        self.api_key = api_key
        self.dataset_id = dataset_id
        self.document_id = document_id
        self.is_qa = True

    def build_dataset(self, dataset_name):
        dataset_info = build_dataset(dataset_name + '_api_build')
        dataset_id = dataset_info["id"]        
        self.dataset_id = dataset_id
    def build_document(self, document_name):
        document_info = build_documents(document_name, self.dataset_id)
        document_id = document_info['document']["id"]
        self.document_id = document_id

    
    def build_dataset_from_local_file(self, local_file_path, dataset_id=None, document_id=None):
        """
        """
        if dataset_id is None:
            dataset_id = self.dataset_id 
        if document_id is None:
            document_id = self.document_id
        index = build_dataset_from_local_json_file(local_file_path, self.api_key, dataset_id, document_id, self.is_qa, 0)
        return index

def get_documents(dataset_id, api_key, page_num=1, page_size=10, search_text=""):
    """
    获取数据集下的文档列表
    
    Args:
        dataset_id (str): 数据集ID
        api_key (str): API密钥
        page_num (int, optional): 页码. 默认为1
        page_size (int, optional): 每页数量. 默认为10
        search_text (str, optional): 搜索文本. 默认为空字符串
    
    Returns:
        dict: 包含文档列表的响应数据，如果请求失败返回None
    """
    url = f"{URL_BASE}/api/core/dataset/collection/list"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "pageNum": page_num,
        "pageSize": page_size,
        "datasetId": dataset_id,
        "parentId": None
    }

    # 只有当search_text非空时才���加到请求数据中
    if search_text and search_text.strip():
        data["searchText"] = search_text.strip()

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        return None
    logging.info(f'get_documents request: {data}, response: {response.json()}')
    try:
        response_json = response.json()
        if response_json["code"] == 200:
            return response_json["data"]
    except:
        logging.error('get documents error: %s', traceback.format_exc())
        return None

def get_documents_name_set(dataset_id, api_key):
    """
    获取数据集下所有文档的名称到ID的映射
    
    Args:
        dataset_id (str): 数据集ID
        api_key (str): API密钥
    
    Returns:
        dict: 文档名称到文档ID的映射字典，如果获取失败返回空字典
    """
    name_to_id = {}
    page_num = 1
    page_size = 100  # 使用较大的页面大小以减少请求次数
    
    while True:
        documents = get_documents(dataset_id, api_key, page_num, page_size)
        if not documents:
            break
            
        # 将当前页的文档名称和ID添加到字典中
        for doc in documents["data"]:
            name_to_id[doc["name"]] = doc["_id"]
            
        # 检查是否还有更多页
        if len(documents["data"]) < page_size:
            break
            
        page_num += 1
    
    return name_to_id

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
