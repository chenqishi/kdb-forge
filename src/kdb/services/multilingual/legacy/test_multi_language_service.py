#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
测试多语言识别服务

使用示例：
1. 启动服务：python multi_language_service.py
2. 运行测试：python test_multi_language_service.py
"""
import requests
import json


def test_predict_language(text, service_url="http://localhost:8007"):
    """
    测试语言预测接口
    
    Args:
        text: 待识别的文本
        service_url: 服务地址
    """
    url = f"{service_url}/lang_predict"
    
    try:
        response = requests.post(
            url,
            json={"text": text},
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"文本: {text}")
            print(f"语言: {result['lang']}")
            print(f"置信度: {result['confidence']:.4f}")
            print(f"原始标签: {result['label']}")
            print("-" * 50)
            return result
        else:
            print(f"错误: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return None


def test_health_check(service_url="http://localhost:8007"):
    """测试健康检查接口"""
    url = f"{service_url}/health"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            result = response.json()
            print(f"健康检查: {result}")
            return result
        else:
            print(f"健康检查失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"健康检查请求失败: {str(e)}")
        return None


if __name__ == "__main__":
    # 首先检查服务是否正常
    print("=" * 50)
    print("健康检查")
    print("=" * 50)
    test_health_check()
    print()
    
    # 测试各种语言的文本
    print("=" * 50)
    print("语言识别测试")
    print("=" * 50)
    
    test_cases = [
        "これはテストです。",  # 日语
        "Hello, how are you?",  # 英语
        "你好，世界！",  # 中文
        "Bonjour le monde",  # 法语
        "Hola mundo",  # 西班牙语
        "Привет мир",  # 俄语
        "안녕하세요",  # 韩语
        "Hallo Welt",  # 德语
        "Ciao mondo",  # 意大利语
        "مرحبا بالعالم",  # 阿拉伯语
        "Olá mundo",  # 葡萄牙语
        "สวัสดีชาวโลก",  # 泰语
    ]
    
    for text in test_cases:
        test_predict_language(text)

