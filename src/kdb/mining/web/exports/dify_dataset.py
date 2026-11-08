from kdb.mining.common.schema.segment_text import parse_segment
from kdb.shared.config.global_config import GLOBAL_CONFIG
from kdb.shared.config.private_values import private_value as _private_value
import json
import logging
import os
import requests
import sys

def build_dataset(name, api_key=_private_value('9e33e55f6fb974e3d97c50d9')):
    """
    """
    url = f"{GLOBAL_CONFIG['dify_api_base']}/datasets"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code != 200:
        return None
    response_json = json.loads(response.text)
    return response_json


def build_documents(text, dataset_id, api_key=_private_value('e54767c18274d0ccd5bbb6ed'), indexing_technique='high_quality'):
    url = f"{GLOBAL_CONFIG['dify_api_base']}/datasets/{dataset_id}/document/create_by_text"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "name": "auto_document",
        "text": text,
        "indexing_technique": indexing_technique,
        "process_rule": {
            "rules": {
                "pre_processing_rules": [{
                    "id": "remove_extra_spaces",
                    "enabled": True
                }, {
                    "id": "remove_urls_emails",
                    "enabled": True
                }],
                "segmentation": {
                    "separator": "\n------\n",
                    "max_tokens": 2000
                }
            },
            "mode": "custom",
            "doc_form": "qa"
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def add_segment(dataset_id, document_id, api_key, content, keywords=None, answer=None):
    url = f"{GLOBAL_CONFIG['dify_api_base']}/datasets/{dataset_id}/documents/{document_id}/segments"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if keywords:
        segments_data = {
            "segments": [
                {
                    "content": content,
                    "keywords": keywords
                }
            ]
        }
    else:
        segments_data = {
            "segments": [
                {
                    "content": content,
                }
            ]
        }
    if answer:
        segments_data['segments'][0]['answer'] = answer
    logging.debug('add_segment: %s %s', headers, segments_data)
    response = requests.post(url, headers=headers, json=segments_data)
    logging.debug('url[%s], response: %s', url, response.text)
    return response.json()


def build_dataset_from_local_file(local_file_path, api_key=_private_value('e68adae757a282dd9f5f2214'), dataset_id=None, document_id=None, qa=1):
    """
    """
    file_name = local_file_path.split("/")[-1]
    file_name, file_extension = os.path.splitext(file_name)
    segmets = open(local_file_path, "r").read().split("\n------\n")
    if dataset_id is None:
        dataset_info = build_dataset(file_name + '_api_build')
        dataset_id = dataset_info["id"]
    if document_id is None:
        document_info = build_documents("init no value", dataset_id)
        document_id = document_info['document']["id"]
    qa = bool(qa)
    for i, segment in enumerate(segmets):
        parse_segment_info = parse_segment(segment)
        logging.info("parse_segment_info: %s", parse_segment_info)
        content = parse_segment_info['content']
        keywords = parse_segment_info['keywords'] + [parse_segment_info['label']] #+ [parse_segment_info['attribute']]
        add_info = add_segment(dataset_id, document_id, api_key=api_key, content=content, keywords=keywords)
        logging.info("add_segment: %s %s", document_id, add_info)


def build_dataset_from_local_json_file(local_file_path, api_key=_private_value('988f2b195c3c4370943299be'), dataset_id=None, document_id=None, qa=1, start_inndex=0):
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
            parse_segment_info = json.loads(line)
            if not qa:
                content = parse_segment_info['title'] + parse_segment_info['content']
            #keywords = parse_segmen  xt_info['keywords'] + [parse_segment_info['label']] #+ [parse_segment_info['attribute']]
                add_info = add_segment(dataset_id, document_id, api_key=api_key, content=content, keywords=None)
            else:
                add_info = add_segment(dataset_id, document_id, api_key=api_key, content=parse_segment_info['title'], keywords=None, answer=parse_segment_info['content'])
            logging.debug("add_segment: %s %s", document_id, add_info)
    return index


def build_dataset_from_local_csv_file(local_file_path, api_key=_private_value('f6cefd188ace53581bb8e626'), dataset_id=None, document_id=None, qa=1, start_index=0):
    """
    从本地CSV文件构建数据集
    """
    file_name = local_file_path.split("/")[-1]
    file_name, file_extension = os.path.splitext(file_name)
    
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
            if index < start_index:
                continue
            print('处理索引: {}'.format(index))
            
            fields = line.strip().split('\t')
            if len(fields) < 2:
                logging.warning(f"第 {index} 行格式不正确,跳过")
                continue
            
            question, answer = fields[0], fields[1]
            
            if qa:
                add_info = add_segment(dataset_id, document_id, api_key=api_key, content=question, keywords=None, answer=answer)
            else:
                content = question + " " + answer
                add_info = add_segment(dataset_id, document_id, api_key=api_key, content=content, keywords=None)
            
            logging.debug("添加片段: %s %s", document_id, add_info)
    
    return index


class DatasetBuilder(object):
    def __init__(self, api_key=_private_value('be643b5992594820091b99ee'), dataset_id=None, document_id=None):
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

    def add_segment(self, content, keywords):
        """
        """
        add_segment(self.dataset_id, self.document_id, self.api_key, content=content, keywords=keywords)
        return True
    
    def build_dataset_from_local_file(self, local_file_path, dataset_id=None, document_id=None):
        """
        """
        if dataset_id is None:
            dataset_id = self.dataset_id 
        if document_id is None:
            document_id = self.document_id
        index = build_dataset_from_local_json_file(local_file_path, self.api_key, dataset_id, document_id, self.is_qa, 0)
        return index


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-08-23
"""


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
