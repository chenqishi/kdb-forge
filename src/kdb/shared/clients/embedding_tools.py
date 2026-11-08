import json
import requests
from typing import Union
from typing import List
import numpy as np
import logging
import time

class AliEmbedding:
    """阿里云 text-embedding-v3 模型调用接口 按照openai标准，因此也可以用于openai模型"""
    
    def __init__(self, config_path: str):
        """
        初始化 AliEmbedding 实例
        
        Args:
            config_path: 配置文件路径，需包含 API key 等信息
        """
        with open(config_path, 'r') as f:
            config = json.load(f)
            
        self.api_key = config.get('DASHSCOPE_API_KEY')
        self.api_url = config.get('DASHSCOPE_API_URL', "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.model = config.get('DASHSCOPE_MODEL', "text-embedding-v3") 
        self.dimension = config.get('DASHSCOPE_DIMENSION', 1024)
        self.encoding_format = config.get('DASHSCOPE_ENCODING_FORMAT', "float")
        self.max_length = config.get('DASHSCOPE_MAX_LENGTH', 5000)
        self.retry_times = config.get('DASHSCOPE_RETRY_TIMES', 3)

    def text2embedding(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        将文本转换为 embedding 向量
        
        Args:
            text: 输入文本，可以是单个字符串或字符串列表
            
        Returns:
            numpy.ndarray: embedding 向量或向量组
            
        Raises:
            Exception: API 调用失败时抛出异常
        """
        if isinstance(text, str):
            input_text = text
        elif isinstance(text, list):
            input_text = text
        else:
            raise ValueError("输入文本必须是字符串或字符串列表")

        if len(input_text) > self.max_length:
            input_text = input_text[:self.max_length]
            
        payload = {
            "model": self.model,
            "input": input_text,
            "dimension": str(self.dimension),
            "encoding_format": self.encoding_format
        }
        for attempt in range(self.retry_times):
            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                response.raise_for_status()
                
                result = response.json()
                if isinstance(text, str):
                    embedding = np.array(result['data'][0]['embedding'])
                else:
                    embedding = np.array([item['embedding'] for item in result['data']])
                    
                return embedding
                
            except Exception as e:
                logging.error(f"获取 embedding 失败: {str(e)}")
                if attempt < self.retry_times - 1:
                    logging.info(f"正在进行第 {attempt + 2} 次重试...")
                    time.sleep(0.5)  # 在重试之前等待5秒
                else:
                    logging.error(f"已达到最大重试次数 ({self.retry_times})，请求失败")
                    raise Exception(f"获取 embedding 失败: {str(e)}")


def test_text2embedding(config_path: str):
    """
    测试 text2embedding 函数
    Args:
        config_path: 配置文件路径
    """
    embedding_tools = AliEmbedding(config_path)
    text = "你好，世界！"
    embedding = embedding_tools.text2embedding(text)
    print(embedding)

if __name__ == '__main__':
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.INFO, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )    
    
    fire.Fire({
        'test_text2embedding': test_text2embedding,
    })