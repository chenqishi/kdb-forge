from kdb.mining.common.schema.segment_text import parse_segment
from kdb.shared.config.global_config import GLOBAL_CONFIG
from kdb.shared.config.private_values import private_value as _private_value
import json
import logging
import os
import requests
import sys

def build_dataset(name, api_key=_private_value('cedc66c3c9e932305b960362')):
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


def build_documents(text, dataset_id, api_key=_private_value('6f3e25b82123aefa7dd4cba1')):
    url = f"{GLOBAL_CONFIG['dify_api_base']}/datasets/{dataset_id}/document/create_by_text"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "name": "auto_cdistonent",
        "text": text,
        "indexing_technique": "high_quality",
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
            "mode": "custom"
        }
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def add_segment(dataset_id, document_id, api_key, content, keywords=None):
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
    
    response = requests.post(url, headers=headers, json=segments_data)
    logging.debug('url[%s], response: %s', url, response.text)
    return response.json()


def build_dataset_from_local_file(local_file_path, api_key=_private_value('4f26e635b2acbd38910bff16'), dataset_id=None, document_id=None):
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
    for i, segment in enumerate(segmets):
        parse_segment_info = parse_segment(segment)
        logging.info("parse_segment_info: %s", parse_segment_info)
        content = parse_segment_info['content']
        keywords = parse_segment_info['keywords'] + [parse_segment_info['label']] #+ [parse_segment_info['attribute']]
        add_info = add_segment(dataset_id, document_id, api_key=api_key, content=content, keywords=keywords)
        logging.info("add_segment: %s %s", document_id, add_info)


def build_dataset_from_local_json_file(local_file_path, api_key=_private_value('e990193701b0a7a7884a784e'), dataset_id=None, document_id=None, start_inndex=0):
    """
    """
    file_name = local_file_path.split("/")[-1]
    file_name, file_extension = os.path.splitext(file_name)
    #segmets = open(local_file_path, "r").read().split("\n------\n")
    if dataset_id is None:
        dataset_info = build_dataset(file_name + '_api_build')
        dataset_id = dataset_info["id"]
    if document_id is None:
        document_info = build_documents("init no value", dataset_id)
        document_id = document_info['document']["id"]
    index = 0 
    with open(local_file_path, 'r') as f:
        for line in f:
            index += 1
            if index < start_inndex:
                continue
            print('prcess_index: {}'.format(index))
            parse_segment_info = json.loads(line)

            content = parse_segment_info['title'] + parse_segment_info['content']
            #keywords = parse_segmen  xt_info['keywords'] + [parse_segment_info['label']] #+ [parse_segment_info['attribute']]
            add_info = add_segment(dataset_id, document_id, api_key=api_key, content=content, keywords=None)
            logging.debug("add_segment: %s %s", document_id, add_info)


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-08-23
"""


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
