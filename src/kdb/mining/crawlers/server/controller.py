#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-01
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



from mp_http_source_util import AtomFeedParser
import crawler_url
import clear_util
import build_dataset_from_api

class ProcessLogitic(object):
    """
    主逻辑处理
    """
    def __init__(self, update_time=None, data_dir=None):
        self.atom_parser = AtomFeedParser()

        self.clearer = clear_util.ContentClearer()
        self.dataset_builder = build_dataset_from_api.DatasetBuilder()
        self.update_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S').timestamp()
        self.data_dir = data_dir

    def main_process(self, params):
        """
        """
        wewe_url = params['wewe_base_url']
        mp_info_list = self.atom_parser.parse_atom_feed(wewe_url)
        valid_crawler_num = 0
        save_file = params['save_file']
        save_file = f'{self.data_dir}/{save_file}'
        max_crawler_num = params.get('max_crawler_num', 10000)
        valid_crawler_num = self.crawler_mp_data(mp_info_list=mp_info_list, save_file=save_file, max_crawler_num=max_crawler_num)
    
        if params['need_add_dataset']:
            dataset_id = params.get('dataset_id', None)
            document_id = params.get('document_id', None)
            self.dataset_builder.build_dataset_from_local_file(local_file_path=save_file, dataset_id=dataset_id, document_id=document_id)
        result_info = {
            'valid_crawler_num': valid_crawler_num,
            'mp_num': len(mp_info_list),        
        }
        return result_info
    
    def crawler_mp_data(self, mp_info_list, save_file, max_crawler_num=10000):
        """
        """
        valid_crawler_num = 0
        with open(save_file, 'w+', encoding='utf-8') as wf:        
            for mp_info in mp_info_list:
                update_time = mp_info['updated']
                dt = datetime.strptime(update_time, '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
                if dt < self.update_time:
                    continue
                result = crawler_url.get_api_result(mp_info['link'])
                content = result['outputs']
                logging.debug('sucess get api result %s %s', mp_info, content)
                clear_content = self.clearer.clear_content(content)
                title = mp_info['title']
                clear_title = self.clearer.clear_content(title)
                data_json = {
                    'title': clear_title,
                    'ori_title': title,
                    'content': clear_content,
                    'ori_content': content,
                    'update_time': update_time,
                    'url': mp_info['link']
                }
                wf.write(json.dumps(data_json, ensure_ascii=False) + '\n')
                valid_crawler_num += 1
                if valid_crawler_num >= max_crawler_num:
                    break
        return valid_crawler_num


def test():
    processer = ProcessLogitic(update_time="2024-08-30 12:00:00", data_dir='./data/crawler_test')
    params = {}
    params['wewe_base_url'] = 'https://lufitairss.zeabur.app'
    params['save_file'] = 'test.json'
    params['need_add_dataset'] = True
    params['dataset_id'] = 'a44baea2-87d8-49e7-825f-432eb9ccadf1'
    params['document_id'] = '628df19b-52c0-472f-9825-60dbcf4789a8'
    params['max_crawler_num'] = 2
    processer.main_process(params)
    




    

        

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()        




            

        
        

    

