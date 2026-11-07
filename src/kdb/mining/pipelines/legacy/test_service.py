#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
任务控制服务测试脚本
演示如何使用各个API接口
"""
import json
import time
import requests
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)

class TaskControlClient:
    """任务控制服务客户端"""
    
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        
    def start_task(self, task_type, task_info):
        """启动任务"""
        url = f"{self.base_url}/start_task"
        data = {
            "task_type": task_type,
            "task_info": task_info
        }
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            logging.info(f"启动任务响应: {result}")
            return result
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None
    
    def query_task(self, task_id):
        """查询任务状态"""
        url = f"{self.base_url}/task_info"
        params = {"task_id": task_id}
        
        try:
            response = requests.get(url, params=params)
            result = response.json()
            logging.info(f"查询任务响应: {result}")
            return result
        except Exception as e:
            logging.error(f"查询任务失败: {e}")
            return None
    
    def stop_task(self, task_id):
        """停止任务"""
        url = f"{self.base_url}/stop_task"
        data = {"task_id": task_id}
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            logging.info(f"停止任务响应: {result}")
            return result
        except Exception as e:
            logging.error(f"停止任务失败: {e}")
            return None
    
    def health_check(self):
        """健康检查"""
        url = f"{self.base_url}/health"
        
        try:
            response = requests.get(url)
            result = response.json()
            logging.info(f"健康检查响应: {result}")
            return result
        except Exception as e:
            logging.error(f"健康检查失败: {e}")
            return None

def test_document_qa_mining():
    """测试文档QA挖掘任务"""
    client = TaskControlClient()
    
    # 健康检查
    logging.info("=== 健康检查 ===")
    client.health_check()
    
    # 准备任务信息
    task_info = {
        "files": [
            {
                "name": "测试文档1",
                "ext": "txt",
                "store_method": "minio",
                "address": "http://example.com/doc1.txt"
            },
            {
                "name": "测试文档2", 
                "ext": "pdf",
                "store_method": "minio",
                "address": "http://example.com/doc2.pdf"
            }
        ],
        "index_name": "test_index_001"
    }
    
    # 启动任务
    logging.info("=== 启动任务 ===")
    start_result = client.start_task("document_qa_mining", task_info)
    
    if start_result and start_result.get("code") == 0:
        task_id = start_result["data"]["task_id"]
        logging.info(f"任务启动成功，task_id: {task_id}")
        
        # 查询任务状态
        logging.info("=== 查询任务状态 ===")
        for i in range(3):
            time.sleep(2)
            client.query_task(task_id)
        
        # 停止任务（如果还在运行）
        logging.info("=== 停止任务 ===")
        client.stop_task(task_id)
        
        # 再次查询状态
        time.sleep(1)
        client.query_task(task_id)
    
    # 最终健康检查
    logging.info("=== 最终健康检查 ===")
    client.health_check()

if __name__ == "__main__":
    logging.info("开始测试任务控制服务...")
    test_document_qa_mining()
    logging.info("测试完成") 