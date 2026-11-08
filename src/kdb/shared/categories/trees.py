#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
from typing import Dict
from typing import List
from typing import Tuple


def get_category_tree(client: str) -> dict:
    """
    获取类目树
    
    Args:
        client: 客户端标识
        
    Returns:
        类目树的响应数据
    """
    url = f"https://admin.marsmind.cc/api/rufit-ai/intranet/knowledge/qaCategory/tree?client={client}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") == "00000":
            return result.get("data", [])
        else:
            print(f"获取类目树失败: {result.get('message')}")
            return []
    except Exception as e:
        print(f"获取类目树异常: {str(e)}")
        return []


def build_category_path_map(category_tree: List[dict], parent_path: str = "") -> Dict[str, str]:
    """
    构建类目路径到categoryId的映射
    
    Args:
        category_tree: 类目树列表
        parent_path: 父类目路径
        
    Returns:
        类目路径 -> categoryId 的映射字典
    """
    path_map = {}
    
    for category in category_tree:
        category_name = category.get("categoryName", "")
        category_id = category.get("categoryId", "")
        
        # 构建当前类目的完整路径
        if parent_path:
            current_path = f"{parent_path}-{category_name}"
        else:
            current_path = category_name
        
        # 添加到映射中
        if category_id:
            path_map[current_path] = category_id
        
        # 递归处理子类目
        children = category.get("children", [])
        if children:
            child_map = build_category_path_map(children, current_path)
            path_map.update(child_map)
    
    return path_map


def build_category_id_to_path_map(category_tree: List[dict], parent_path: str = "") -> Dict[str, str]:
    """
    构建categoryId到类目路径的反向映射
    
    Args:
        category_tree: 类目树列表
        parent_path: 父类目路径
        
    Returns:
        categoryId -> 类目路径 的映射字典
    """
    id_map = {}
    
    for category in category_tree:
        category_name = category.get("categoryName", "")
        category_id = category.get("categoryId", "")
        
        # 构建当前类目的完整路径
        if parent_path:
            current_path = f"{parent_path}-{category_name}"
        else:
            current_path = category_name
        
        # 添加到映射中
        if category_id:
            id_map[category_id] = current_path
        
        # 递归处理子类目
        children = category.get("children", [])
        if children:
            child_map = build_category_id_to_path_map(children, current_path)
            id_map.update(child_map)
    
    return id_map


def get_category_maps(client: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    获取类目的双向映射字典
    
    Args:
        client: 客户端标识
        
    Returns:
        Tuple[Dict, Dict]: (name_to_id_map, id_to_name_map)
            - name_to_id_map: 类目路径 -> categoryId
            - id_to_name_map: categoryId -> 类目路径
    """
    category_tree = get_category_tree(client)
    if not category_tree:
        return {}, {}
    
    name_to_id_map = build_category_path_map(category_tree)
    id_to_name_map = build_category_id_to_path_map(category_tree)
    return name_to_id_map, id_to_name_map


def build_leaf_to_full_path_map(category_tree: List[dict], parent_path: str = "") -> Dict[str, List[str]]:
    """
    构建叶子节点名称到完整路径的映射
    
    注意：同一个叶子节点名称可能对应多个完整路径
    
    Args:
        category_tree: 类目树列表
        parent_path: 父类目路径
        
    Returns:
        叶子节点名称 -> [完整路径列表] 的映射字典
    """
    leaf_map = {}
    
    for category in category_tree:
        category_name = category.get("categoryName", "")
        
        # 构建当前类目的完整路径
        if parent_path:
            current_path = f"{parent_path}-{category_name}"
        else:
            current_path = category_name
        
        children = category.get("children", [])
        
        if children:
            # 有子节点，递归处理
            child_map = build_leaf_to_full_path_map(children, current_path)
            for leaf_name, paths in child_map.items():
                leaf_map.setdefault(leaf_name, []).extend(paths)
        else:
            # 是叶子节点，添加映射
            leaf_map.setdefault(category_name, []).append(current_path)
    
    return leaf_map


def get_leaf_to_full_path_map(client: str) -> Dict[str, List[str]]:
    """
    获取叶子节点到完整路径的映射
    
    Args:
        client: 客户端标识
        
    Returns:
        叶子节点名称 -> [完整路径列表] 的映射字典
    """
    category_tree = get_category_tree(client)
    if not category_tree:
        return {}
    
    return build_leaf_to_full_path_map(category_tree)
