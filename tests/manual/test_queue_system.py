#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
测试任务队列系统的脚本
"""
import requests
import json
import time

# 服务地址
BASE_URL = "http://localhost:6000"

def test_start_task():
    """测试启动任务"""
    url = f"{BASE_URL}/start_task"
    
    # 测试文档QA挖掘任务
    data = {
        "task_type": "document_qa_mining",
        "task_info": {
            "files": ["test1.txt", "test2.txt"],
            "index_name": "test_index"
        }
    }
    
    response = requests.post(url, json=data)
    print(f"启动文档QA挖掘任务: {response.status_code}")
    print(f"响应: {response.json()}")
    
    time.sleep(1)
    
    # 测试聊天QA挖掘任务
    data = {
        "task_type": "chat_qa_mining",
        "task_info": {
            "client": "test_client",
            "user": "test_user",
            "app_id": "test_app",
            "start_time": "20240101000000",
            "end_time": "20240131235959"
        }
    }
    
    response = requests.post(url, json=data)
    print(f"启动聊天QA挖掘任务: {response.status_code}")
    print(f"响应: {response.json()}")

def test_health_check():
    """测试健康检查"""
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    print(f"健康检查: {response.status_code}")
    print(f"响应: {response.json()}")

def test_task_info(task_id):
    """测试查询任务信息"""
    url = f"{BASE_URL}/task_info"
    data = {"task_id": task_id}
    response = requests.post(url, json=data)
    print(f"查询任务信息: {response.status_code}")
    print(f"响应: {response.json()}")

if __name__ == "__main__":
    print("=== 测试任务队列系统 ===")
    
    # 健康检查
    test_health_check()
    print()
    
    # 启动任务
    test_start_task()
    print()
    
    # 再次健康检查，查看队列状态
    test_health_check()
