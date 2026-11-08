import os
import re

def get_index_file_name(from_file_name):
    from_file_name = from_file_name.strip('/')
    if from_file_name.startswith('http'):
        # 从URL中提取最后的路径部分
        url_path = from_file_name.split('/')[-1]
        # 移除查询参数（如果有）
        url_path = url_path.split('?')[0]
        # 移除文件扩展名
        base_name = os.path.splitext(url_path)[0]
        # 替换非法字符
        sheet_name = re.sub(r'[^\w\s-]', '', base_name)
        return sheet_name
    else:
        return os.path.splitext(os.path.basename(from_file_name))[0]


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-17
"""
