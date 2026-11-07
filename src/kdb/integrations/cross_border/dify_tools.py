#!/usr/bin/env python
# -*- coding:utf8 -*-

import json
import logging
import requests
import time
import traceback

class DifyWorkFlowRequest(object):
    def __init__(self, api_base=None, api_key=None, max_retries=3):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries


    def request_dify(self, paragraph):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': {
                'paragraph': paragraph
            },
            "response_mode": "blocking",
            "user": "test"
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify API，请求内容: {payload}")
                response = requests.post(f"{self.api_base}/workflows/run", headers=headers, json=payload, timeout=600)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                
                result = response.json()
                if result['data']['status'] == 'failed':
                    logging.error(f"Dify请求失败: {result['data']['error']} api_key: {self.api_key}")
                    if attempt < self.max_retries - 1:
                        logging.info(f"正在进行第{attempt + 2}次重试...")
                        time.sleep(5)  # 在重试之前等待5秒
                        continue
                    else:
                        return None
                
                return result['data']['outputs']['Final']
            except KeyError as e:
                logging.error(f"响应中缺少字段: {str(e)}")
                logging.error(f"完整响应内容: {response.text}")
            except requests.exceptions.Timeout:
                logging.error("请求超时（10分钟）")
            except requests.exceptions.RequestException as e:
                logging.error(f"请求异常: {str(e)}")
                logging.error(f"请求URL: {self.api_base}/workflows/run")
                logging.error(f"请求头: {headers}")
                logging.error(f"请求体: {payload}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"调用Dify API时发生错误: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logging.info(f"正在进行第{attempt + 2}次重试...")
                time.sleep(5)  # 在重试之前等待5秒
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None


class DifyChatFlowRequest(object):
    def __init__(self, api_base=None, api_key=None, max_retries=3):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries

    def request_dify(self, query, conversion_id='', inputs=None):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': inputs or {},
            "query": query,
            "response_mode": "blocking",
            "user": "test",
            "conversation_id": conversion_id
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify Chat API，{self.api_base}请求内容: {payload}")
                response = requests.post(f"{self.api_base}/chat-messages", headers=headers, json=payload, timeout=600)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                logging.info(f'model[{self.api_base}] response: {response.text}')
                return response.json()
                
            except requests.exceptions.Timeout:
                logging.error("请求超时（10分钟）")
            except requests.exceptions.RequestException as e:
                logging.error(f"请求异常: {str(e)}")
                logging.error(f"请求URL: {self.api_base}/chat-messages")
                logging.error(f"请求头: {headers}")
                logging.error(f"请求体: {payload}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"调用Dify Chat API时发生错误: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logging.info(f"正在进行第{attempt + 2}次重试...")
                time.sleep(5)  # 在重试之前等待5秒
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None
