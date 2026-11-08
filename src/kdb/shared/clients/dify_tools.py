#!/usr/bin/env python
# -*- coding:utf8 -*-

import json
import logging
import requests
import time
import traceback
import os
from typing import Optional
from typing import Dict
from typing import Any

class DifyWorkFlowRequest(object):
    def __init__(self, api_base=None, api_key=None, max_retries=3, system_prompt=None, timeout=600):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = None

    def request_dify(self, paragraph, other_inputs=None):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        inputs = {}
        #logging.info(f"paragraph: {paragraph} other_inputs: {other_inputs} system_prompt: {self.system_prompt}")
        if paragraph:
            inputs['paragraph'] = paragraph
        if other_inputs:
            inputs.update(other_inputs)
        if self.system_prompt:
            inputs['system_prompt'] = self.system_prompt
        if len(inputs) <= 0:
            raise ValueError("inputs is empt, paragraph: %s, other_inputs: %s, system_prompt: %s" % (paragraph, other_inputs, self.system_prompt))
        payload = {
            "inputs": inputs,
            "response_mode": "blocking",
            "user": "test"
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify API，请求内容: {payload}")
                response = requests.post(f"{self.api_base}/workflows/run", headers=headers, json=payload, timeout=self.timeout)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}, api_key:{self.api_key}, request{payload}")
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
                logging.error("请求超时（%s秒）", self.timeout)
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

    def request_dify(self, query, inputs, conversion_id=''):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }

        if not inputs:
            inputs = {}

        payload = {
            'inputs': inputs,
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


def upload_file_to_dify(base_url: str, api_key: str, file_path: str, user_id: str = "default-user") -> Optional[Dict[str, Any]]:
    """
    上传文件到 Dify 服务器
    
    Args:
        base_url: Dify 服务器基础 URL
        api_key: API 密钥
        file_path: 本地文件路径
        user_id: 用户 ID
        
    Returns:
        成功返回文件信息字典，失败返回 None
    """
    try:
        # 构建完整的 URL
        upload_url = f"{base_url.rstrip('/')}/files/upload"
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logging.error(f"文件不存在: {file_path}")
            return None
            
        # 准备请求头
        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        logging.info("开始上传文件...")
        
        # 获取文件的 MIME 类型
        file_extension = os.path.splitext(file_path)[1].lower()
        mime_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        }
        mime_type = mime_type_map.get(file_extension, 'application/octet-stream')
        
        with open(file_path, 'rb') as file:
            # 准备文件和表单数据
            files = {
                'file': (os.path.basename(file_path), file, mime_type)
            }
            data = {
                'user': user_id
            }
            
            # 发送请求
            response = requests.post(
                upload_url,
                headers=headers,
                files=files,
                data=data
            )
            
            if response.status_code == 200 or response.status_code == 201:
                logging.info("文件上传成功")
                logging.debug("返回结果: %s", response.text)
                return response.json()
            else:
                logging.error(f"文件上传失败，状态码: {response.status_code}, 响应: {response.text}, url: {upload_url}, api_key: {api_key}, user: {user_id}")
                return None
                
    except Exception as e:
        logging.error(f"上传文件时发生错误: {str(e)}")
        return None


class DIfyWorkFlowMlutiVisionRequest(object):
    def __init__(self, api_base=None, api_key=None, user='default', max_retries=3):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries
        self.user = user

    def request_dify(self, paragraph, input_file=None, file_type="image"):
        """
        请求 Dify API，支持文本和文件输入
        
        Args:
            paragraph: 文本输入
            input_file: 输入文件路径（可选）
            file_type: 文件类型，默认为"image"
            
        Returns:
            处理结果或 None（如果失败）
        """
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        # 准备基础 payload
        payload = {
            'inputs': {
                'paragraph': paragraph
            },
            "response_mode": "blocking",
            "user": self.user
        }
        
        # 如果提供了文件，先上传文件
        if input_file and not input_file.startswith('http'):
            try:
                logging.info(f"开始上传文件: {input_file}")
                file_info = upload_file_to_dify(self.api_base, self.api_key,  input_file, self.user)
                
                if not file_info:
                    logging.error("文件上传失败")
                    return None
                    
                # 将文件信息添加到 payload
                file_id = file_info.get('id')
                logging.info(f"文件上传成功，file_id: {file_id}")
                payload['inputs']['input_file'] = {
                    "transfer_method": "local_file",
                    "upload_file_id": file_id,
                    "type": file_type
                }
                
            except Exception as e:
                logging.error(f"处理文件时发生错误: {str(e)}")
                return None

        elif input_file and input_file.startswith('http'):
            try:
                logging.info(f"使用远程文件URL: {input_file}")
                payload['inputs']['input_file'] = {
                    "transfer_method": "remote_url",
                    "url": input_file,
                    "type": file_type
                }
            except Exception as e:
                logging.error(f"处理远程文件时发生错误: {str(e)}")
                return None
        
        # 发送请求并处理响应
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify API，请求内容: {payload}")
                response = requests.post(
                    f"{self.api_base}/workflows/run",
                    headers=headers,
                    json=payload,
                    timeout=600
                )
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                
                result = response.json()
                if result['data']['status'] == 'failed':
                    logging.error(f"Dify请求失败: {result['data']['error']} api_key: {self.api_key}")
                    if attempt < self.max_retries - 1:
                        logging.info(f"正在进行第{attempt + 2}次重试...")
                        time.sleep(5)
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
                time.sleep(5)
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None

