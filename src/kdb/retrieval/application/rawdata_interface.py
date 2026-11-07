import json
import os
import hashlib
from typing import Iterator, Dict, Any, Union, List

def gen_data_id(data: Dict[str, Any]) -> str:
    """
    生成数据的唯一ID
    Args:
        data: 输入的数据字典
    Returns:
        str: 生成的唯一ID
    """
    # 将数据转换为排序后的JSON字符串，确保相同数据生成相同的hash
    sorted_data = json.dumps(data, sort_keys=True)
    # 使用MD5生成唯一ID
    return hashlib.md5(sorted_data.encode()).hexdigest()

class LocalRawDataInterface:
    """本地原始数据接口类，用于读取本地文件或目录中的数据"""
    
    def __init__(self, file_path: str):
        """
        初始化接口
        Args:
            file_path: 文件或目录路径
        """
        self.file_path = file_path
        
    def _read_single_file(self, file_path: str, is_need_id: bool = True) -> Iterator[Dict[str, Any]]:
        """
        读取单个文件中的JSON数据
        Args:
            file_path: 文件路径
        Yields:
            Dict: 每行解析后的JSON数据，并添加唯一ID
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    fields = line.strip().split('\t')
                    data = json.loads(fields[-1])
                    if isinstance(data, dict):
                        if '_id' not in data and is_need_id:
                            data['_id'] = gen_data_id(data)
                        yield data
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"处理文件 {file_path} 时发生错误: {str(e)}")
                    continue
    
    def read_data(self, is_need_id: bool = True) -> Iterator[Dict[str, Any]]:
        """
        读取文件或目录中的所有数据
        Returns:
            Iterator[Dict]: 数据迭代器，每个元素为一条数据
        """
        if os.path.isfile(self.file_path):
            yield from self._read_single_file(self.file_path, is_need_id)
        elif os.path.isdir(self.file_path):
            for root, _, files in os.walk(self.file_path):
                for file in files:
                    if file.endswith('.txt'):
                        file_path = os.path.join(root, file)
                        yield from self._read_single_file(file_path, is_need_id)
        else:
            raise FileNotFoundError(f"路径 {self.file_path} 不存在")
