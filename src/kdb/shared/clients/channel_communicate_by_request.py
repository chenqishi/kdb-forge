#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-19
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
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError

class ChannelRequestCommunicate(object):
    def __init__(self, base_url):
        self.base_url = base_url
        if not self.base_url.endswith('/'):
            self.base_url += '/'

    def send_wx(self, content, receiver, is_group=False, data_type='TEXT'):
        url = self.base_url + 'send'
        data = {
            "content": content,
            "receiver": receiver,
            "is_group": str(is_group).lower(),
            "data_type": data_type
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            
            try:
                result = response.json()
                if result.get('success'):
                    return True, "消息发送成功"
                else:
                    return False, result.get('message', '未知错误')
            except RequestsJSONDecodeError:
                # 如果无法解析JSON，则返回原始响应内容
                return False, f"服务器响应不是有效的JSON格式。原始响应: {response.text}"
                
        except requests.RequestException as e:
            tb = traceback.format_exc()
            logging.error(f"请求发送失败: {tb}")
            return False, f"请求发送失败: {str(e)}"
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"发送过程中出现未知错误: {tb}")
            return False, f"发送过程中出现未知错误: {str(e)}"


if __name__ == '__main__':
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')    
    channel_request_communicate = ChannelRequestCommunicate()
    print(channel_request_communicate.send_wx("hello", "石"))
