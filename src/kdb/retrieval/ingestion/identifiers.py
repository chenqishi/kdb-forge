from typing import Any
from typing import Dict
import hashlib

def gen_data_id(data: Dict[str, Any]) -> str:
    """
    生成数据的唯一ID，使用title、content和data_type的组合进行MD5计算
    Args:
        data: 输入的数据字典
    Returns:
        str: 生成的唯一ID
    """
    # 获取字段值，不存在则使用空字符串
    title = data.get('title', '')
    content = data.get('content', '')
    data_type = data.get('data_type', '')

    # 组合字符串并计算MD5
    id_str = f"{title}_{content}_{data_type}"
    return hashlib.md5(id_str.encode('utf-8')).hexdigest()
