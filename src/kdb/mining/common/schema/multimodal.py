from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import json
import logging
import os
import re
import traceback

def _load_multimodal_mapping(multimodal_mapping_path: Optional[str]) -> Dict[str, Any]:
    """
    加载多模态映射字典
    
    Args:
        multimodal_mapping_path: 多模态映射文件路径（JSON格式）
    
    Returns:
        Dict[str, Any]: URL到多模态内容的映射字典 {url: item_info}
    """
    if not multimodal_mapping_path or not os.path.exists(multimodal_mapping_path):
        logging.warning(f"多模态映射文件不存在: {multimodal_mapping_path}")
        return {}

    try:
        with open(multimodal_mapping_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 支持两种格式:
            # 1. 直接的 {url: item} 映射
            # 2. {page: [items]} 格式，需要转换
            if isinstance(data, dict):
                # 检查是否是 {page: [items]} 格式
                first_key = next(iter(data), None)
                if first_key and isinstance(data[first_key], list):
                    # 转换格式
                    multimodal_map = {}
                    for page, items in data.items():
                        for item in items:
                            if item.get('type') != 'text' and item.get('public_url'):
                                multimodal_map[item['public_url']] = item
                    return multimodal_map
                else:
                    # 已经是 {url: item} 格式
                    return data
            return {}
    except Exception as exc:
        logging.error(f"加载多模态映射文件失败: {multimodal_mapping_path}, error: {exc}")
        traceback.print_exc()
        return {}


def add_multimodal_contents_to_content(content: str, multimodal_map_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    将混合了文本和URL的内容解析拆分成结构化的多模态内容数组
    
    Args:
        content: 文本内容，可能包含URL
        multimodal_map_dict: URL到多模态内容的映射字典 {url: item_info}
    
    Returns:
        List[Dict[str, Any]]: 多模态内容数组
        
    multimodal_contents 格式示例:
    [
        {"type": "text", "content": "这是文本内容"},
        {"type": "image", "path": "bucket/path/to/image.png", "fileName": "image.png", "url": None},
        {"type": "file", "path": None, "fileName": "doc.pdf", "url": "https://external.com/doc.pdf"}
    ]
    """
    if not content or not isinstance(content, str):
        return []

    if not multimodal_map_dict:
        # 没有多模态映射，返回纯文本
        return [{"type": "text", "content": content}]

    # 1. 提取文本中的所有 URL（支持 http/https，支持连续无分隔URL的拆分）
    url_pattern = re.compile(
        r'(https?://'
        r'(?:[-\w.@])+'
        r'(?::[0-9]+)?'
        r'(?:/(?:(?!https?://)[^\s<>"\'`\]])*)?'
        r'(?:\?(?:(?!https?://)[^\s<>"\'`\]\]])*)?'
        r'(?:#(?:(?!https?://)[^\s<>"\'`\]\]])*)?)',
        re.IGNORECASE
    )

    # 找到所有 URL 及其位置
    url_matches = []
    for match in url_pattern.finditer(content):
        url = match.group(0)
        start_pos = match.start()
        end_pos = match.end()
        url_matches.append({
            'url': url,
            'start': start_pos,
            'end': end_pos,
            'in_map': url in multimodal_map_dict
        })

    # 2. 按照 URL 位置切分文本，构建 items
    items = []
    current_pos = 0

    for url_info in url_matches:
        # 添加 URL 前的文本
        if current_pos < url_info['start']:
            text_before = content[current_pos:url_info['start']].strip()
            if text_before:
                items.append({
                    'type': 'text',
                    'content': text_before
                })

        # 处理 URL
        if url_info['in_map']:
            # URL 在映射中，创建多模态 item
            multimodal_item = multimodal_map_dict[url_info['url']]
            item = _create_multimodal_item(multimodal_item)
            items.append(item)
        else:
            # URL 不在映射中，作为普通文本处理
            items.append({
                'type': 'text',
                'content': url_info['url']
            })

        current_pos = url_info['end']

    # 添加最后剩余的文本
    if current_pos < len(content):
        text_after = content[current_pos:].strip()
        if text_after:
            items.append({
                'type': 'text',
                'content': text_after
            })

    # 3. 合并相邻的 text 类型 item
    multimodal_contents = _merge_adjacent_text_items(items)

    return multimodal_contents


def _create_multimodal_item(multimodal_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据多模态映射字典中的 item 创建标准格式的 multimodal content item
    
    Args:
        multimodal_item: 从 multimodal_map_dict 获取的 item，包含：
            - type: 类型（image, video, audio等）
            - s3_path: S3存储路径（如果是内部存储）
            - fileName: 文件名
            - extern_url: 外部链接URL（如果是外链）
            - public_url: 公开访问URL
            - image_ocr: OCR识别结果（可选）
            - image_understanding: 图像理解结果（可选）
    
    Returns:
        dict: 标准格式的 multimodal content item
    """
    item_type = multimodal_item.get('type', 'file')
    s3_path = multimodal_item.get('s3_path')
    file_name = multimodal_item.get('fileName')
    extern_url = multimodal_item.get('extern_url')
    public_url = multimodal_item.get('public_url')
    image_ocr = multimodal_item.get('image_ocr')
    image_understanding = multimodal_item.get('image_understanding')

    # 构建标准格式的 item
    result = {
        'type': item_type,
    }

    # 如果有 s3_path，表示是内部存储
    if s3_path:
        result['path'] = s3_path
        result['fileName'] = file_name or ''
        result['url'] = public_url or extern_url or ''
    # 如果有 extern_url，表示是外部链接
    elif extern_url:
        result['path'] = None
        result['fileName'] = file_name or ''
        result['url'] = extern_url or ''
    # 兜底：使用 public_url
    else:
        result['path'] = None
        result['fileName'] = file_name or ''
        result['url'] = public_url or ''

    # 添加 OCR 和图像理解结果（如果存在）
    if image_ocr:
        result['image_ocr'] = image_ocr
    if image_understanding:
        result['image_understanding'] = image_understanding

    return result


def _merge_adjacent_text_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并相邻的 text 类型 item
    
    Args:
        items: item 列表
    
    Returns:
        list: 合并后的 item 列表
    """
    if not items:
        return []

    merged = []
    current_text_parts = []

    for item in items:
        if item['type'] == 'text':
            # 收集相邻的 text 内容
            current_text_parts.append(item['content'])
        else:
            # 遇到非 text 类型，先保存之前收集的 text
            if current_text_parts:
                merged_text = '\n'.join(current_text_parts)
                if merged_text.strip():
                    merged.append({
                        'type': 'text',
                        'content': merged_text
                    })
                current_text_parts = []

            # 添加当前非 text item
            merged.append(item)

    # 处理最后剩余的 text
    if current_text_parts:
        merged_text = '\n'.join(current_text_parts)
        if merged_text.strip():
            merged.append({
                'type': 'text',
                'content': merged_text
            })

    return merged
