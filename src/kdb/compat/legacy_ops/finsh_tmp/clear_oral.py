#!/usr/bin/env python
# -*- coding:utf8 -*-

from kdb.shared.config.private_values import private_value as _private_value
import logging
import requests
import time
import traceback
import sys
from config_tools.config import GLOBAL_CONFIG

# 全局变量
#API_KEY = '[PRIVATE_CREDENTIAL_REDACTED]'
API_KEY = _private_value('2ad2fdfacf4b140e11dc6ee9')
API_BASE = GLOBAL_CONFIG['dify_api_base']
USER = 'user_test'

class ClearOralRequest(object):
    def __init__(self, max_retries=3):
        self.max_retries = max_retries
        
    def request(self, run_number):
        headers = {
            'Authorization': f"Bearer {API_KEY}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': {
                'run_number': run_number
            },
            "response_mode": "blocking",
            "user": USER
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Clear Oral API，{API_BASE}请求内容: {payload}")
                response = requests.post(f"{API_BASE}/workflows/run", headers=headers, json=payload, timeout=600)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                
                result = response.json()
                if result['data']['status'] == 'failed':
                    logging.error(f"请求失败: {result['data']['error']} api_key: {API_KEY}")
                    if attempt < self.max_retries - 1:
                        logging.info(f"正在进行第{attempt + 2}次重试...")
                        time.sleep(5)
                        continue
                    else:
                        return None
                
                return result['data']['outputs']['done']
                
            except KeyError as e:
                logging.error(f"响应中缺少字段: {str(e)}")
                logging.error(f"完整响应内容: {response.text}")
            except requests.exceptions.Timeout:
                logging.error("请求超时（10分钟）")
            except requests.exceptions.RequestException as e:
                logging.error(f"请求异常: {str(e)}")
                logging.error(f"请求URL: {API_BASE}/workflows/run")
                logging.error(f"请求头: {headers}")
                logging.error(f"请求体: {payload}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"调用Clear Oral API时发生错误: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logging.info(f"正在进行第{attempt + 2}次重试...")
                time.sleep(5)  # 在重试之前等待5秒
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None

def run_batch(start_num, end_num):
    """
    按顺序执行一批请求
    
    Args:
        start_num: 起始数字
        end_num: 结束数字
    """
    if None in [API_KEY, API_BASE, USER]:
        logging.error("请先设置全局变量 API_KEY, API_BASE 和 USER")
        return
        
    requester = ClearOralRequest()
    
    for num in range(start_num, end_num + 1):
        result = requester.request(num)
        
        if result is None:
            print(f"第{num}次请求结果失败")
            logging.error(f"处理数字 {num} 失败，result: {result}")
        else:
            print(f"第{num}次请求结果成功")
            logging.info(f"成功处理数字 {num}, result: {result}")


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'run_batch': run_batch,
    })
    