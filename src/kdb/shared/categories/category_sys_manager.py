#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
from typing import Dict, List, Optional, Set
import time

from kdb.shared.categories.category_sys_util import get_category_tree, build_category_path_map


def insert_category(client: str, userId: str, category_name: str, parent_id: Optional[str] = None) -> Optional[str]:
    """
    插入单个类目
    
    Args:
        client: 客户端标识
        userId: 用户ID
        category_name: 类目名称
        parent_id: 父类目ID（可选）
        
    Returns:
        插入成功返回新的categoryId，失败返回None
    """
    url = "https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/saveByIntranet"
    
    payload = {
        "client": client,
        "userId": userId,
        "categoryName": category_name
    }
    
    if parent_id:
        payload["parentId"] = parent_id
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") == "00000":
            data = result.get("data", {})
            category_id = data.get("categoryId")
            print(f"成功插入类目: {category_name}, categoryId: {category_id}")
            return category_id
        else:
            print(f"插入类目失败: {category_name}, 原因: {result.get('message')}")
            return None
    except Exception as e:
        print(f"插入类目异常: {category_name}, 错误: {str(e)}")
        return None


def parse_category_file(category_file: str) -> List[str]:
    """
    解析类目文件
    
    Args:
        category_file: 类目文件路径
        
    Returns:
        类目路径列表
    """
    categories = []
    
    try:
        with open(category_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # 忽略空行和注释行
                    categories.append(line)
    except Exception as e:
        print(f"读取类目文件失败: {str(e)}")
        return []
    
    return categories


def expand_categories_with_parents(categories: List[str]) -> List[str]:
    """
    扩展类目列表，自动补全所有缺失的父类目
    
    例如: 如果有"财务-支付-人民币"，会自动补充"财务"和"财务-支付"
    
    Args:
        categories: 类目路径列表
        
    Returns:
        包含所有父类目的完整类目路径列表（去重）
    """
    expanded = set()
    
    for category_path in categories:
        parts = category_path.split('-')
        # 生成所有层级的类目路径
        for i in range(1, len(parts) + 1):
            parent_path = '-'.join(parts[:i])
            expanded.add(parent_path)
    
    return list(expanded)


def sort_categories_by_level(categories: List[str]) -> List[str]:
    """
    按层级排序类目，确保父类目在子类目之前
    
    Args:
        categories: 类目路径列表
        
    Returns:
        排序后的类目路径列表
    """
    # 按照'-'分隔符的数量排序，数量少的在前（层级浅）
    return sorted(categories, key=lambda x: x.count('-'))


def batch_insert_category_from_file(category_file: str, client: str, userId: str) -> Dict[str, int]:
    """
    从文件批量插入类目
    
    Args:
        category_file: 类目文件路径，每行一个类目路径（格式如"财务"或"财务-支付"或"财务-支付-人民币"）
        client: 客户端标识
        userId: 用户ID
        
    Returns:
        统计信息字典，包含成功数、失败数、跳过数
    """
    print(f"开始批量插入类目...")
    print(f"文件: {category_file}")
    print(f"客户端: {client}")
    print(f"用户ID: {userId}")
    print("-" * 50)
    
    # 1. 读取类目文件
    categories = parse_category_file(category_file)
    if not categories:
        print("类目文件为空或读取失败")
        return {"success": 0, "failed": 0, "skipped": 0}
    
    print(f"从文件中读取到 {len(categories)} 个类目")
    
    # 2. 扩展类目列表，自动补全所有父类目
    expanded_categories = expand_categories_with_parents(categories)
    added_parents = set(expanded_categories) - set(categories)
    print(f"补全父类目后，共 {len(expanded_categories)} 个类目需要处理")
    if added_parents:
        print(f"自动补全了 {len(added_parents)} 个父类目:")
        for parent in sorted(added_parents, key=lambda x: x.count('-')):
            print(f"  + {parent}")
    
    # 3. 获取现有类目树
    print("正在获取现有类目树...")
    category_tree = get_category_tree(client)
    
    # 4. 构建类目路径映射
    path_map = build_category_path_map(category_tree)
    print(f"现有类目数量: {len(path_map)}")
    if path_map:
        print("现有类目路径示例:")
        for path in list(path_map.keys())[:5]:
            print(f"  - {path} -> {path_map[path]}")
    print("-" * 50)
    
    # 5. 按层级排序类目
    sorted_categories = sort_categories_by_level(expanded_categories)
    
    # 6. 依次插入类目
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for category_path in sorted_categories:
        # 检查是否已存在
        if category_path in path_map:
            print(f"[跳过] 类目已存在: {category_path}")
            skipped_count += 1
            continue
        
        # 解析类目路径
        parts = category_path.split('-')
        category_name = parts[-1]  # 当前类目名称
        
        # 获取父类目ID
        parent_id = None
        if len(parts) > 1:
            # 有父类目，构建父类目路径
            parent_path = '-'.join(parts[:-1])
            parent_id = path_map.get(parent_path)
            
            if not parent_id:
                print(f"[失败] 找不到父类目: {parent_path}，无法插入: {category_path}")
                failed_count += 1
                continue
        
        # 插入类目
        print(f"[插入] 类目: {category_path}, 父ID: {parent_id if parent_id else '无'}")
        new_category_id = insert_category(client, userId, category_name, parent_id)
        
        if new_category_id:
            # 更新路径映射，以便后续子类目使用
            path_map[category_path] = new_category_id
            success_count += 1
            # 稍微延迟，避免请求过快
            time.sleep(0.2)
        else:
            failed_count += 1
    
    # 7. 输出统计信息
    print("-" * 50)
    print("批量插入完成！")
    print(f"原始类目数: {len(categories)}")
    print(f"扩展后类目数: {len(sorted_categories)}")
    print(f"成功插入: {success_count}")
    print(f"失败: {failed_count}")
    print(f"跳过（已存在）: {skipped_count}")
    
    return {
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count
    }


if __name__ == "__main__":
    # 测试示例
    # 创建一个测试文件，展示混合层级的类目
    import logging
    import fire
    import sys
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    fire.Fire()