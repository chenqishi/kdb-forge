import json
import os
from openpyxl import Workbook, load_workbook
from openpyxl_image_loader import SheetImageLoader
import logging
import sys
import re
from typing import List, Dict, Any, Union, Optional
import traceback
from commons.common_utils import load_map_dict
import binascii
from PIL import Image
import io
from openpyxl.utils import get_column_letter

_EXCEL_COLUMN_ALIASES: Dict[str, List[str]] = {
    'title':             ['title', 'question', '问题', '标题', '问法', 'Question', 'q', 'Q',
                          '質問', 'タイトル', '設問'],
    'content':           ['content', 'answer', '答案', '内容', '回复', 'Answer', 'a', 'A',
                          '回答', '答え'],
    'indexes':           ['indexes', 'index', 'keyword', '检索词', '关键词', 'キーワード', '索引'],
    'synonyms_title':    ['synonyms_title', 'synonyms', '相似问', '同义问'],
    'supply_info_query': ['supply_info_query', '补充查询', '扩展查询'],
    'platform':          ['platform', '平台'],
    'category':          ['category', '分类'],
    'from_scene':        ['from_scene', '场景'],
    'data_type':         ['data_type', '数据类型'],
    'from_type':         ['from_type', '来源类型'],
    'audit_result':      ['audit_result', '审核结果'],
    'image_path':        ['image_path', '图片路径'],
    'image_data':        ['image_data', '图片数据'],
}


def map_excel_columns(headers: List) -> Optional[Dict[str, int]]:
    """
    Map an Excel header row to canonical field names.

    Returns {canonical_name: col_index} when both title and content can be resolved,
    or None when the mapping is incomplete (caller should fall back to unstructured parser).
    """
    alias_lookup: Dict[str, str] = {}
    for canonical, aliases in _EXCEL_COLUMN_ALIASES.items():
        for alias in aliases:
            alias_lookup[str(alias).strip().lower()] = canonical

    mapping: Dict[str, int] = {}
    for idx, header in enumerate(headers):
        if header is None:
            continue
        key = str(header).strip().lower()
        canonical = alias_lookup.get(key)
        if canonical and canonical not in mapping:
            mapping[canonical] = idx

    if 'title' not in mapping or 'content' not in mapping:
        return None
    return mapping


def _canonical_excel_field(header: Any, zero_based_idx: int, canonical_by_idx: Dict[int, str]) -> str:
    """Return a canonical field name when the sheet was confidently mapped."""
    return canonical_by_idx.get(zero_based_idx, header)


# 标准 QA 表头（英文/规范字段字面量）。只有 title/content 或
# question/answer 成对组合即视为 standard_qa；其余可被 map_excel_columns
# 解析的（含中文别名）归为 mapped_qa。
_STANDARD_QA_HEADER_PAIRS = (
    frozenset({'title', 'content'}),
    frozenset({'question', 'answer'}),
)


def classify_excel_upload(excel_file: str, sample_row_limit: int = 5) -> Dict[str, Any]:
    """
    判定上传 Excel 应走哪条处理链路（deterministic，不调用 LLM）。

    读取首个含表头的 sheet 的表头与若干样本行，返回路由判定：
      - standard_qa：表头已含标准 title/content 或 Question/Answer 成对字面量。
      - mapped_qa：表头可经 map_excel_columns 解析出 title + content（含中文别名）。
      - unstructured_excel：无法映射，走非结构化文档知识流程。

    Returns:
        Dict[str, Any]: {
            "mode": "standard_qa" | "mapped_qa" | "unstructured_excel",
            "mapping": Optional[Dict[str, int]],   # canonical_name -> 0-based col idx
            "reason": str,
            "confidence": float,                   # 0~1
            "headers": List[Any],
            "sheet_name": Optional[str],
            "sample_rows": List[List[Any]],
        }
    """
    result: Dict[str, Any] = {
        "mode": "unstructured_excel",
        "mapping": None,
        "reason": "",
        "confidence": 0.0,
        "headers": [],
        "sheet_name": None,
        "sample_rows": [],
    }

    try:
        wb = load_workbook(excel_file, read_only=True, data_only=True)
    except Exception as exc:
        # 无法读取（损坏/格式异常）时，安全降级到非结构化处理，绝不抛错中断路由。
        result["reason"] = f"无法读取 Excel，降级为非结构化处理: {exc}"
        result["confidence"] = 0.3
        return result

    try:
        headers: List[Any] = []
        sheet_name = None
        sample_rows: List[List[Any]] = []

        # 找到第一个含非空表头的 sheet
        for name in wb.sheetnames:
            ws = wb[name]
            row_iter = ws.iter_rows(values_only=True)
            first_row = next(row_iter, None)
            if first_row is None:
                continue
            candidate_headers = list(first_row)
            if not any(h is not None and str(h).strip() for h in candidate_headers):
                continue
            headers = candidate_headers
            sheet_name = name
            for sample in row_iter:
                if len(sample_rows) >= sample_row_limit:
                    break
                sample_rows.append(list(sample))
            break
    finally:
        wb.close()

    result["headers"] = headers
    result["sheet_name"] = sheet_name
    result["sample_rows"] = sample_rows

    if not headers:
        result["reason"] = "未找到含表头的 sheet，降级为非结构化处理"
        result["confidence"] = 0.3
        return result

    normalized = {str(h).strip().lower() for h in headers if h is not None and str(h).strip()}
    mapping = map_excel_columns(headers)
    result["mapping"] = mapping

    if any(pair.issubset(normalized) for pair in _STANDARD_QA_HEADER_PAIRS):
        result["mode"] = "standard_qa"
        result["confidence"] = 0.95
        result["reason"] = "表头包含标准 title/content 或 Question/Answer 字段对"
        return result

    if mapping:
        # 用样本行的 title/content 填充率辅助置信度（不改变判定结果）。
        title_idx = mapping.get('title')
        content_idx = mapping.get('content')
        filled = 0
        for row in sample_rows:
            t = row[title_idx] if title_idx is not None and title_idx < len(row) else None
            c = row[content_idx] if content_idx is not None and content_idx < len(row) else None
            if t is not None and str(t).strip() and c is not None and str(c).strip():
                filled += 1
        ratio = (filled / len(sample_rows)) if sample_rows else 1.0
        result["mode"] = "mapped_qa"
        result["confidence"] = round(min(0.9, 0.6 + 0.3 * ratio), 3)
        result["reason"] = (
            f"表头可映射为 QA 表 (title/content 别名命中)，样本行填充率={ratio:.2f}"
        )
        return result

    result["mode"] = "unstructured_excel"
    result["confidence"] = 0.6
    result["reason"] = "表头无法解析出 title+content，走非结构化文档知识流程"
    return result


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

def load_white_name_permission_dict(white_name_file):
    """
    加载白名单文件
    """
    white_name_dict = dict()
    with open(white_name_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            platform = columns[0]
            writers = set(columns[1].split('|'))
            if len(columns) > 2:
                permissions = set(columns[2].split('|'))
            else:
                permissions = set(['high'])
            white_name_dict[platform] = {'writers': writers, 'permissions': permissions}
    return white_name_dict

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

def json_to_excel(json_data, wb, platform=None):
    for item in json_data:
        sheet_name = get_index_file_name(item['from_file_name'])
        logging.info(f'from_file_name: {item["from_file_name"]}, sheet_name: {sheet_name}')
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(sheet_name)
            if platform:
                ws.append(["platform", "问题", "答案"])
            else:
                ws.append(["问题", "答案"])
        else:
            ws = wb[sheet_name]
        if platform:
            ws.append([platform, item['q'], item['a']])
        else:
            ws.append([item['q'], item['a']])

def json_to_excel_has_quality(json_data, wb, platform=None):
    """
    带有质量标签的json数据转换为excel
    """
    for k, json_list in json_data.items():
        for item in json_list:
            # 修改sheet名称的生成方式
            base_name = get_index_file_name(item['from_file_name'])
            suffix = f'_{k}'
            max_base_length = 31 - len(suffix)  # 预留suffix的长度
            
            # 如果base_name过长，从中间截取
            if len(base_name) > max_base_length:
                half_length = max_base_length // 2
                base_name = base_name[:half_length] + '...' + base_name[-half_length:]
            
            sheet_name = f'{base_name}{suffix}'
            sheet_name = re.sub(r'[^\w\s-]', '', sheet_name)  # 替换非字母数字的字符为下划线
            
            logging.info(f'sheet_name: {sheet_name}')
            
            if sheet_name not in wb.sheetnames:
                ws = wb.create_sheet(sheet_name)
                if platform:
                    ws.append(["平台", "问题", "答案", '组号', 'quality_tag'])
                else:
                    ws.append(["问题", "答案", '组号', 'quality_tag'])
            else:
                ws = wb[sheet_name]
            if platform:
                ws.append([platform, item['q'], item['a'], item['group'], '|'.join(item['quality_info'])])
            else:
                ws.append([item['q'], item['a'], item['group'], '|'.join(item['quality_info'])])

def json_to_excel_mid_quality(json_data, wb, platform=None):
    """
    带有mid质量标签的json数据转换为excel
    """
    for item in json_data:
        # 修改sheet名称的生成方式
        base_name = get_index_file_name(item['from_file_name'])
        sheet_name = f'{base_name}'
        sheet_name = re.sub(r'[^\w\s-]', '', sheet_name)  # 替换非字母数字的字符为下划线
        logging.info(f'sheet_name: {sheet_name}')
        
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(sheet_name)
            if platform:
                ws.append(["平台", "问题", "答案", '组号', 'quality_tag', 'reason'])
            else:
                ws.append(["问题", "答案", '组号', 'quality_tag', 'reason'])
        else:
            ws = wb[sheet_name]
        if platform:
            ws.append([platform, item['q'], item['a'], item['group'], '|'.join(item['quality_info']), item.get('reason', '')])
        else:
            ws.append([item['q'], item['a'], item['group'], '|'.join(item['quality_info']), item.get('reason', '')])   
            
def batch_json_to_excel(batch_file, excel_file, field_num=3, mode=0):
    # 如果excel文件不存在，创建新的工作簿
    if not os.path.exists(excel_file):
        wb = Workbook()
        wb.remove(wb.active)  # 删除默认创建的sheet
    else:
        wb = load_workbook(excel_file)
    
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if len(columns) >= 4:
                json_file = columns[field_num]
                with open(json_file, 'r', encoding='utf-8') as jf:
                    json_data = json.load(jf)
                    if mode == 0:
                        json_to_excel(json_data, wb)
                    else:
                        json_to_excel_has_quality(json_data, wb)
    
    wb.save(excel_file)


def qajson_to_line_text(qa_json_list, add_index=False):
    trans_texts = list()

    for index, item in enumerate(qa_json_list):
        q = item['q']
        a = item['a']
        if add_index:
            one_qa = f'{index+1}.问题:{q}\n答案:{a}'
        else:
            one_qa = f'问题:{q}\n答案:{a}'
        trans_texts.append(one_qa)
    trans_text = '\n###\n'.join(trans_texts)
    return trans_text

def output_qa_json_trans_result(qa_json_file, add_index=1, wrtite_file=None):
    """
    """
    add_index = bool(add_index)
    qa_json_list = json.load(open(qa_json_file, 'r', encoding='utf-8'))
    trans_text = qajson_to_line_text(qa_json_list, add_index)
    if wrtite_file:
        with open(wrtite_file, 'w', encoding='utf-8') as f:
            f.write(trans_text)
    else:
        print(trans_text)

IMAGE_PLACEHOLDER_GUIDE = (
    '【本文中的 [图1] [图2] … 是文档里的插图。'
    '紧跟其后的「里的文字」「内容说明」就是这张图的内容，请据此作答。'
    '如果某张图能直观说明答案（截图、流程图、对比表），'
    '请在答案末尾单独一行写上对应的 [图N] 标记，系统会自动还原成图片；'
    '不要写图片网址。答案必须先给出完整的文字说明，不能只给 [图N] 标记。】\n'
)

IMAGE_PLACEHOLDER_RE = re.compile(r'[\[【]图(\d+)[\]】]')


def _placeholder_for(url, placeholder_map):
    """同一张图始终拿到同一个编号。

    编号必须按 URL 建一次映射：`merge_segment_content` 在一次生成里会被调用多次
    （整篇一次、分段各一次），如果每次调用都重新计数，同一张图会拿到不同编号，
    模型看到 [图76] 这种大数字还容易把占位符本身当成提问对象。
    """
    for tag, mapped in placeholder_map.items():
        if mapped == url:
            return tag
    tag = '[图%d]' % (len(placeholder_map) + 1)
    placeholder_map[tag] = url
    return tag


def restore_image_placeholders(text, placeholder_map):
    """把答案里的 [图N] 还原成 markdown 图片。

    URL 从映射表取，**不经过模型**——模型只需要抄对 4 个字符的标记。
    实测让模型直接抄 40 字符的图片 URL 会抄错（把日期段重复三遍、多个 URL 粘连），
    改成占位符后链接正确率 100%。标记对不上时返回空串，最坏情况是少一张图，不会产生坏链。
    """
    if not text or not placeholder_map:
        return text or ''

    def _sub(match):
        url = placeholder_map.get('[图%s]' % match.group(1))
        return '![嵌入图片](%s "Flowchart")' % url if url else ''

    return IMAGE_PLACEHOLDER_RE.sub(_sub, text)


def strip_image_placeholders(text):
    """问题里不该出现占位符，直接去掉。"""
    return IMAGE_PLACEHOLDER_RE.sub('', text or '').strip()


# 多模态图床的 URL。占位符模式下模型看不到这类地址，答案里出现就是它自己编的。
_MULTIMODAL_URL_RE = re.compile(
    r'!?\[[^\]]*\]\(\s*https?://[^)\s]*kgmultimodal[^)\s]*\s*\)'
    r'|https?://[^\s)\]"\'>]*kgmultimodal[^\s)\]"\'>]*'
)


def strip_hallucinated_image_urls(text):
    """去掉答案里模型自己编的图床 URL。

    占位符模式下模型根本看不到图片地址，写出来的必然是幻觉。而且实测它会**退化成复读**
    （`/20260807/20260807/...` 重复几百次），这一条就能吃光后续质检调用的 token 预算，
    导致整批 QA 拿不到质量标签、全部降级——一次实跑里 42 条只解析出 1 条。
    真正的配图由 `restore_image_placeholders` 按映射还原，不依赖模型写地址。
    """
    if not text:
        return text or ''
    cleaned = _MULTIMODAL_URL_RE.sub('', text)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


def merge_segment_content(data_json, segment, need_add_page_num=False, use_image_content=0,
                          add_image_context=0, image_placeholder_map=None):
    """
    合并指定页面范围内的文本内容。

    :param data_json: 包含所有页面内容的JSON数据
    :param segment: 包含页面范围的字典
    :param need_add_page_num: 是否需要添加页码信息
    :param add_image_context: 1 时把 OCR/图片理解直接铺在图片位置
    :param image_placeholder_map: 传入一个 dict 即启用**占位符模式**：
        图片位置输出 `[图N]` + 该图的 OCR/图片理解，真实 URL 只留在这个 map 里，
        生成完再用 `restore_image_placeholders` 还原。
        既让模型看得到图里的内容，又不用它抄 URL。
    :return: 合并后的文本内容
    """
    start_page, end_page = segment['pages']
    segment_content = ''
    logging.info(f'start merge segment content, start_page: {start_page}, end_page: {end_page} use_image_content: {use_image_content}, add_image_context: {add_image_context}')
    for page_num in range(start_page, end_page + 1):
        page_values = data_json.get(str(page_num), [])
        one_page_content = ''
        for one_value in page_values:
            if one_value.get('type') == 'text':
                one_segment_content = one_value.get('text_content', '')
                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content
            elif use_image_content and one_value.get('type') == 'image':
                if not one_value.get("is_valid", False):
                    continue
                public_url = one_value.get('public_url', '')
                ocr = one_value.get('image_ocr', '')
                image_understanding = one_value.get('image_understanding', '')
                #name = one_value.get('name', '')

                if image_placeholder_map is not None:
                    if not public_url:
                        continue
                    tag = _placeholder_for(public_url, image_placeholder_map)
                    parts = [tag]
                    if ocr:
                        parts.append('%s里的文字：%s' % (tag, ocr))
                    if image_understanding:
                        parts.append('%s的内容说明：%s' % (tag, image_understanding))
                    one_segment_content = '\n'.join(parts)
                elif add_image_context:
                    one_segment_content = f'![嵌入图片]({public_url} "Flowchart")'
                    if ocr:                        
                        one_segment_content = f'{one_segment_content}\n{public_url}的ocr理解为:\n<image_ocr>{ocr}</image_ocr>'
                    if image_understanding:
                        one_segment_content = f'{one_segment_content}\n{public_url}的图片理解为:\n<image_understanding>{image_understanding}</image_understanding>'

                else:
                    one_segment_content = f'{public_url}'

                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content
        
        if one_page_content:
            if need_add_page_num:
                one_page_content = f'第{page_num}页内容如下:\n{one_page_content}'
            segment_content = segment_content + '\n' + one_page_content if segment_content else one_page_content

    # 占位符模式下把用法说明放在正文最前面，模型才知道 [图N] 是什么、该怎么用。
    # 放在这里而不是调用方，是因为每次调用都是一次独立的 prompt，都得带上这个约定。
    if image_placeholder_map is not None and segment_content:
        segment_content = IMAGE_PLACEHOLDER_GUIDE + segment_content

    return segment_content

def trans_page_content_to_text(page_content_json, add_page_num=1, pages=None):
    """
    """
    pages = pages if pages else [1, len(page_content_json)]
    trans_text = merge_segment_content(page_content_json, {'pages': pages}, add_page_num, use_image_content=1, add_image_context=0)    # add_image_context为0 ，因为已经增加multimodal_contents字段, image_context在检索的时候实时拼接
    return trans_text

def output_page_content_trans_result(page_content_file, add_page_num=1, wrtite_file=None):
    """
    """
    add_page_num = bool(add_page_num)
    page_content_json = json.load(open(page_content_file, 'r', encoding='utf-8'))
    trans_text = trans_page_content_to_text(page_content_json, add_page_num)
    if wrtite_file:
        with open(wrtite_file, 'w', encoding='utf-8') as f:
            f.write(trans_text)
    else:
        print(trans_text)

def batch_split_json_quality_to_excel(batch_file, high_quality_excel_file, mid_quality_excel_file, low_quality_excel_file=None, field_num=3, platform_field_num=None):
    """
    将高质量和中等质量的数据分别写入不同的Excel文件
    
    Args:
        batch_file: 批处理文件路径
        high_quality_excel_file: 高质量数据的Excel文件路径
        mid_quality_excel_file: 中等质量数据的Excel文件路径
        field_num: 批处理文件中JSON文件路径所在的列号
    """
    # 修改工作簿创建和加载逻辑
    try:
        if os.path.exists(high_quality_excel_file):
            try:
                high_wb = load_workbook(high_quality_excel_file)
            except Exception as e:
                logging.warning(f"无法加载高质量Excel文件，创建新文件: {str(e)}")
                high_wb = Workbook()
                high_wb.remove(high_wb.active)
        else:
            high_wb = Workbook()
            high_wb.remove(high_wb.active)
            
        if os.path.exists(mid_quality_excel_file):
            try:
                mid_wb = load_workbook(mid_quality_excel_file)
            except Exception as e:
                logging.warning(f"无法加载中等质量Excel文件，创建新文件: {str(e)}")
                mid_wb = Workbook()
                mid_wb.remove(mid_wb.active)
        else:
            mid_wb = Workbook()
            mid_wb.remove(mid_wb.active)
        if low_quality_excel_file:
            low_wb = Workbook()
            low_wb.remove(low_wb.active)
            
        with open(batch_file, 'r', encoding='utf-8') as f:
            for line in f:
                columns = line.strip().split('\t')
                if platform_field_num is not None:
                    platform = columns[platform_field_num]
                else:
                    platform = None
                
                if len(columns) > field_num:
                    json_file = columns[field_num]
                    logging.info(f'process json_file: {json_file}')
                    with open(json_file, 'r', encoding='utf-8') as jf:
                        try:
                            json_data = json.load(jf)
                        except:
                            tb = traceback.format_exc()
                            logging.error(f'process json_file: {json_file} error: {tb}')
                            continue
                        # 分别处理高质量和中等质量数据
                        if 'high' in json_data:
                            json_to_excel(json_data['high'], high_wb, platform)
                        if 'mid' in json_data:
                            json_to_excel_mid_quality(json_data['mid'], mid_wb, platform)
                        if 'low' in json_data and low_quality_excel_file:
                            json_to_excel_mid_quality(json_data['low'], low_wb, platform)
        
        # 确保即使workbook为空也会保存文件
        if not high_wb.sheetnames:
            ws = high_wb.create_sheet("Sheet1")  # 创建一个空的sheet
        high_wb.save(high_quality_excel_file)
        
        if not mid_wb.sheetnames:
            ws = mid_wb.create_sheet("Sheet1")
        mid_wb.save(mid_quality_excel_file)
        
        if low_quality_excel_file:
            if not low_wb.sheetnames:
                ws = low_wb.create_sheet("Sheet1")
            low_wb.save(low_quality_excel_file)
    
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        raise


def batch_select_high_quality_qa_to_json(batch_file, field_num=6, platform_field_num=None):
    """
    批量选择高质量的QA数据并转换为JSON文件
    """
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if platform_field_num is not None:
                platform = columns[platform_field_num]
            else:
                platform = None
            logging.info(f'platform_field_num: {platform_field_num}, platform: {platform}')
            if len(columns) > field_num:
                json_file = columns[field_num]
                logging.info(f'start process json_file: {json_file}')

                with open(json_file, 'r', encoding='utf-8') as jf:
                    json_data = json.load(jf)
                    # 分别处理高质量和中等质量数据                    
                    qa_list = json_data.get('high', [])
                    for qa in qa_list:
                        from_file_name = qa.get('from_file_name', '')
                        file_name = get_index_file_name(from_file_name)
                        trans_info = {'title': qa['q'], 'content': qa['a'], 'document_name': file_name} # document_name 用于在fastgpt下建立不同的document
                        if platform:
                            trans_info['platform'] = platform
                        print(json.dumps(trans_info, ensure_ascii=False))


def batch_select_high_quality_qa_and_white_answer_to_json(batch_file, white_name_file, field_num=6):
    """
    批量选择高质量以及在白名单中的数据QA数据并转换为JSON文件
    """
    white_name_dict = load_white_name_permission_dict(white_name_file)            
    with open(batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            columns = line.strip().split('\t')
            if len(columns) > field_num:
                json_file = columns[field_num]
                logging.info(f'start process json_file: {json_file}')
                with open(json_file, 'r', encoding='utf-8') as jf:
                    
                    json_data = json.load(jf)
                    # 分别处理高质量和中等质量数据                    
                    qa_list = list()
                    for k, v_list in json_data.items():
                        for v in v_list:
                            v['quality'] = k
                        qa_list.extend(v_list)
                    for qa in qa_list:
                        from_file_name = qa.get('from_file_name', '')
                        platform = qa.get('platform', '')

                        file_name = qa.get('from_user', '')
                        if file_name not in white_name_dict.get(platform, {}).get('writers', set()):
                            continue
                        if qa['quality'] not in white_name_dict.get(platform, {}).get('permissions', set()):
                            continue
                        trans_info = {'title': qa['q'], 'content': qa['a'], 'document_name': file_name} # document_name 用于在fastgpt下建立不同的document
                        if platform:
                            trans_info['platform'] = platform
                        print(json.dumps(trans_info, ensure_ascii=False))
def excel_to_qa_json(excel_file: str):
    """
    将带平台格式的excel数据转换为qa json格式
    
    Args:
        excel_file: Excel文件路径
    
    输出格式示例:
    {
        "title": "问题内容",
        "content": "答案内容",
        "document_name": "sheet名称",
        "platform": "平台名称"
    }
    """
    try:
        wb = load_workbook(excel_file, read_only=False, data_only=True)  # data_only=True 会读取公式的结果值
        
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # 获取表头
            headers = [cell.value for cell in next(ws.rows)]
            
            # 检查必要的列是否存在
            platform_idx = headers.index("平台") if "平台" in headers else None
            question_idx = headers.index("问题")
            answer_idx = headers.index("答案")
            
            # 遍历数据行
            for row in list(ws.rows)[1:]:  # 跳过表头
                trans_info = {
                    "title": row[question_idx].value,
                    "content": row[answer_idx].value,
                    "document_name": sheet_name
                }
                
                if platform_idx is not None:
                    platform = row[platform_idx].value
                    if platform:  # 只在平台值非空时添加
                        trans_info["platform"] = platform
                
                print(json.dumps(trans_info, ensure_ascii=False))
                
    except Exception as e:
        logging.error(f"处理Excel文件时发生错误: {str(e)}")
        raise

def trans_qa_to_search_data(qa_data: Dict[str, Any], platform=None, from_type_extra=None, category_id=None, category_name=None, task_id=None, multimodal_map_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    将QA数据转换为搜索索引格式
    Args:
        qa_data: QA数据，包含q、a等字段
        task_id: 任务ID
        multimodal_map_dict: 多模态映射字典（可选）
    Returns:
        Dict[str, Any]: 搜索索引格式的数据
    """
    # 获取文件类型
    from_file = qa_data.get('from_file_name', '')
    file_type = 'doc'  # 默认为doc
    if from_file:
        if from_file.lower().endswith('.pdf'):
            file_type = 'pdf'
        elif from_file.lower().endswith(('.doc', '.docx')):
            file_type = 'doc'
        elif from_file.lower().endswith('.html'):
            file_type = 'html'
        elif from_file.lower().startswith('http'):
            file_type = 'html'
    if 'group_name' in qa_data:
        from_type = 'chat'
    else:
        from_type = file_type


    
    quality_level = qa_data.get('quality_level', '')

    
    # 判断质量等级
    upstream_ext_info = qa_data.get('ext_info') if isinstance(qa_data.get('ext_info'), dict) else {}
    quality_info = qa_data.get('quality_info', upstream_ext_info.get('quality_info', []))
    platform = qa_data.get('platform') or platform
    client = qa_data.get('client') or platform

    from_type = from_type_extra if from_type_extra else from_type
    
    # 获取 content
    content = qa_data.get('a', '')
    
    # 构建搜索索引数据
    search_data = {
        'title': qa_data.get('q', ''),  # 问题作为标题
        'content': content,  # 答案作为内容
        'synonyms_title': [],  # 暂无同义标题
        'data_type': 'qa',  # QA类型
        'platform': platform,
        'client': client,
        'audit_result': -1,  # 默认未审核
        'quality_level': quality_level,
        'from_type': from_type,
        'indexes': [
            {'text': qa_data.get('q', '')}  # 将问题添加为检索文本
        ],
        'ext_info': {
            'from_file_name': qa_data.get('from_file_name', upstream_ext_info.get('from_file_name', '')),
            'from_page': qa_data.get('from_page', upstream_ext_info.get('from_page', [])),
            'quality_info': quality_info
        }
    }

    # 兼容 2026-06 生产聊天 QA 已经写入 ES 的扩展字段。
    # 仅恢复历史白名单，不透传任意 info/ext_info，避免 ES mapping 膨胀和类型冲突。
    legacy_ext_fields = (
        'quality_reason', 'knowledge_type', 'business_tags', 'scenario_tags',
        'entity_tags', 'es_tags', 'reuse_scope', 'should_enter_reuse_evaluation',
        'confidence', 'source_quote', 'candidate_answer_time', 'from_user',
        'source', 'client', 'marketplace', 'model_platform', 'supplement',
        'supplement_mapping_error',
    )
    for field_name in legacy_ext_fields:
        if field_name in qa_data:
            search_data['ext_info'][field_name] = qa_data[field_name]
        elif field_name in upstream_ext_info:
            search_data['ext_info'][field_name] = upstream_ext_info[field_name]

    qa_tags = qa_data.get('tags', upstream_ext_info.get('tags'))
    if isinstance(qa_tags, list):
        search_data['tags'] = qa_tags

    # 审核决策保留在顶层，供 ES 写入前的程序闸门读取。
    # SearchDataInterface 处理单条数据时会把非 schema 字段归入 ext_info。
    for field_name in (
        'review_decision', 'review_reason_codes', 'review_reason', 'review_model',
        'review_version', 'extractor_quality_level', 'grounded', 'knowledge_scope',
        'sensitive', 'temporary', 'valid_until', 'auto_import',
    ):
        if field_name in qa_data:
            search_data[field_name] = qa_data[field_name]
        elif field_name in upstream_ext_info:
            search_data[field_name] = upstream_ext_info[field_name]

    # 保留抽取和证据扩展字段。这些字段不参与顶层检索，但审核、分类和追溯需要。
    for field_name in (
        'marketplace', 'model_platform', 'source_quote', 'source_message_ids',
        'source_user_id', 'source_identity', 'source_identity_reason', 'from_user',
        'confidence', 'reuse_scope', 'is_qualified',
    ):
        if field_name in qa_data:
            search_data['ext_info'][field_name] = qa_data[field_name]
        elif field_name in upstream_ext_info:
            search_data['ext_info'][field_name] = upstream_ext_info[field_name]
    
    # 处理 multimodal_contents
    if content:
        if multimodal_map_dict:
            # 有多模态映射，处理混合内容
            multimodal_contents = add_multimodal_contents_to_content(content, multimodal_map_dict)
        else:
            # 没有多模态映射，将纯文本转为 multimodal_contents 格式
            multimodal_contents = [{"type": "text", "content": content}]
        
        if multimodal_contents:
            search_data['multimodal_contents'] = multimodal_contents
    
    # 优先保留 QA 上游显式传入的 category_infos。
    explicit_category_infos = qa_data.get('category_infos')
    if isinstance(explicit_category_infos, list) and explicit_category_infos:
        normalized_category_infos = []
        for item in explicit_category_infos:
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            if normalized_item.get('category_id') in (None, '') and normalized_item.get('categoryId') not in (None, ''):
                normalized_item['category_id'] = normalized_item['categoryId']
            if normalized_item.get('category_name') in (None, '') and normalized_item.get('categoryName') not in (None, ''):
                normalized_item['category_name'] = normalized_item['categoryName']
            normalized_item.pop('categoryId', None)
            normalized_item.pop('categoryName', None)
            normalized_category_infos.append(normalized_item)
        search_data['category_infos'] = normalized_category_infos
    else:
        category_value = qa_data.get('category')
        if isinstance(category_value, dict):
            category_id_qa_data = (
                category_value.get('category_id') or category_value.get('categoryId') or
                qa_data.get('category_id') or qa_data.get('categoryId')
            )
            category_name_qa_data = (
                category_value.get('category_name') or category_value.get('categoryName') or
                qa_data.get('category_name') or qa_data.get('categoryName')
            )
        else:
            category_id_qa_data = qa_data.get('category_id') or qa_data.get('categoryId')
            category_name_qa_data = (
                qa_data.get('category_name') or qa_data.get('categoryName') or category_value
            )

        category_id = category_id_qa_data or category_id
        category_name = category_name_qa_data or category_name
        category_source = 'manual'

        # Payoneer Olive 的一级类目就是平台名。任务未显式传 category 时，
        # 把抽取模型已识别的 marketplace/model_platform 作为待解析类目名。
        # 这里不猜 category_id，由 SearchDataInterface 用生产类目树解析。
        client_norm = str(client or '').strip().lower().replace('_', '')
        if not category_id and not category_name and client_norm == 'payoneerolive':
            inferred_category = str(
                qa_data.get('marketplace') or qa_data.get('model_platform') or ''
            ).strip()
            inferred_norm = inferred_category.lower().replace('_', '')
            if inferred_category and inferred_norm not in {'unknown', 'mix', 'payoneerolive', 'payoneer'}:
                category_name = inferred_category
                category_source = 'model_platform'

        category_ids = [item.strip() for item in str(category_id or '').split(',') if item.strip()]
        category_names = [item.strip() for item in str(category_name or '').split(',') if item.strip()]
        category_infos = []
        for index in range(max(len(category_ids), len(category_names))):
            category_info = {
                'score': 1.0,
                'source': category_source,
            }
            if index < len(category_ids):
                category_info['category_id'] = category_ids[index]
            if index < len(category_names):
                category_info['category_name'] = category_names[index]
            category_infos.append(category_info)
        if category_infos:
            search_data['category_infos'] = category_infos
    if task_id:
        search_data['task_id'] = task_id
        # 旧版 Payoneer Olive chat_auto 文档以 flag 标识任务批次；保留同值别名。
        search_data['flag'] = qa_data.get('flag') or task_id
    elif qa_data.get('flag') not in (None, ''):
        search_data['flag'] = qa_data['flag']
    if 'from_chat_history' in qa_data:
        search_data['ext_info']['from_chat_history'] = qa_data['from_chat_history']
    elif 'from_chat_history' in upstream_ext_info:
        search_data['ext_info']['from_chat_history'] = upstream_ext_info['from_chat_history']
    return search_data

def trans_qa_to_search_data_one_file(qa_json_file, output_file_handle,  platform=None, from_type=None, category_id=None, category_name=None, task_id=None, multimodal_map_dict: Optional[Dict[str, Any]] = None):
    """
    将qa_file中的所有文件转换成search_index 中insert所需格式
    Args:
        qa_json_file: QA JSON文件路径
        output_file_handle: 输出文件句柄或路径
        platform: 平台名称
        from_type: 来源类型
        category_id: 分类ID
        category_name: 分类名称
        task_id: 任务ID
        multimodal_map_dict: 多模态映射字典（可选，直接传入字典）
    """
    if isinstance(output_file_handle, str):
        of = open(output_file_handle, 'w', encoding='utf-8')

    else:
        of = output_file_handle
    
    with open(qa_json_file, 'r', encoding='utf-8') as jf:
        try:
            json_data = json.load(jf)
        except:
            tb = traceback.format_exc()
            logging.error(f'process json_file: {qa_json_file} error: {tb}')
            return 
        def _add_attr(qa_info_list, attr_name, attr_value):
            for qa_info in qa_info_list:
                qa_info[attr_name] = attr_value
        all_qa_info_list = list()
        # 分别处理高质量和中等质量数据
        if 'high' in json_data:
            qa_info_list = json_data['high']
            if platform:
                _add_attr(qa_info_list, 'platform', platform)
            _add_attr(qa_info_list, 'quality_level', 'high')
            all_qa_info_list.extend(qa_info_list)
        if 'mid' in json_data:
            qa_info_list = json_data['mid']
            if platform:
                _add_attr(qa_info_list, 'platform', platform)
            _add_attr(qa_info_list, 'quality_level', 'mid')
            all_qa_info_list.extend(qa_info_list)
        if 'low' in json_data:
            qa_info_list = json_data['low']
            if platform:
                _add_attr(qa_info_list, 'platform', platform)
            _add_attr(qa_info_list, 'quality_level', 'low')
            all_qa_info_list.extend(qa_info_list)
        for qa_info in all_qa_info_list:
            search_data = trans_qa_to_search_data(qa_info, platform, from_type, category_id, category_name, task_id, multimodal_map_dict)
            of.write(json.dumps(search_data, ensure_ascii=False) + '\n')


def batch_trans_qa_to_search_data(batch_file, output_file, field_num=6, platform_field_num=0, from_type=None, category_id=None, category_name=None, task_id=None, multimodal_mapping_path: Optional[str] = None):
    """
    将batch_file中的所有文件转换成search_index 中insert所需格式
    Args:
        batch_file: 批处理文件路径
        output_file: 输出文件路径
        field_num: QA JSON文件所在字段位置
        platform_field_num: 平台字段位置
        from_type: 来源类型
        category_id: 分类ID
        category_name: 分类名称
        task_id: 任务ID
        multimodal_mapping_path: 多模态信息（图片，文件，video）映射文件路径（可选）
    """
    # 加载多模态映射（如果提供了路径）
    multimodal_map_dict = None
    if multimodal_mapping_path:
        multimodal_map_dict = _load_multimodal_mapping(multimodal_mapping_path)
        logging.info(f"加载多模态映射: {multimodal_mapping_path}, 映射数量: {len(multimodal_map_dict)}")
    
    # 修改工作簿创建和加载逻辑
    try:
        with open(batch_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as of:
            for line in f:
                columns = line.strip().split('\t')
                if platform_field_num is not None:
                    platform = columns[platform_field_num]
                else:
                    platform = None
                
                if len(columns) > field_num:
                    json_file = columns[field_num]
                    logging.info(f'process json_file: {json_file}')
                    trans_qa_to_search_data_one_file(json_file, of, platform, from_type, category_id, category_name, task_id, multimodal_map_dict)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"生成search_index数据时发生错误: {str(e)}")
        raise

def trans_doc_segment_to_search_data(segment_info: Dict[str, Any], category_id=None, category_name=None, task_id=None, multimodal_map_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    将文档片段数据转换为搜索索引格式
    Args:
        segment_info: 文档片段数据，包含content、keywords等字段
        task_id: 任务ID
        multimodal_map_dict: 多模态映射字典（可选）
    Returns:
        Dict[str, Any]: 搜索索引格式的数据
    """
    # 获取文件类型
    from_file = segment_info.get('from_file_name', '')
    file_type = 'doc'  # 默认为doc
    if from_file:
        if from_file.lower().endswith('.pdf'):
            file_type = 'pdf'
        elif from_file.lower().endswith(('.doc', '.docx')):
            file_type = 'doc'
        elif from_file.lower().endswith('.html'):
            file_type = 'html'
    
    # 转换content为文本
    content = segment_info.get('content', {})
    pages = segment_info.get('pages', [])
    if content and pages:
        pages_keys = [int(p) for p in content.keys()]
        start = min(pages_keys)
        end = max(pages_keys)
        content_text = trans_page_content_to_text(content, add_page_num=1, pages=[start, end])
    else:
        content_text = ''
    
    # 构建检索文本列表。
    # 空 text 会让 DashScope embedding 报 400，进而整条 segment 入库失败，所以逐项滤空——
    # 列表非空不代表元素非空：模型输出「[phrases]:」后面空着时会得到 ['']。
    def _clean_index_terms(values):
        return [str(v).strip() for v in (values or []) if v is not None and str(v).strip()]

    indexes = []
    # 添加关键词组合
    keywords = _clean_index_terms(segment_info.get('keywords'))
    if keywords:
        indexes.append({'text': ','.join(keywords)})
    # 添加短语组合
    for phrase in _clean_index_terms(segment_info.get('phrases')):
        indexes.append({'text': phrase})
    # 添加每个主题
    for topic in _clean_index_terms(segment_info.get('topics')):
        indexes.append({'text': topic})
    # 添加文件名作为索引
    if segment_info.get('index_file_name') and str(segment_info['index_file_name']).strip():
        indexes.append({'text': str(segment_info['index_file_name']).strip()})
    

    # 构建搜索索引数据
    search_data = {
        'content': content_text,  # 转换后的文本内容
        'data_type': 'segment',  # segment类型
        'platform': segment_info.get('platform', ''),
        'audit_result': -1,  # 默认未审核
        'quality_level': 'high',  # 文档片段默认高等质量
        'from_type': file_type,
        'indexes': indexes,
        'keywords': segment_info.get('keywords', []),
        'ext_info': {
            'from_file_name': segment_info.get('from_file_name', ''),
            'start_page': pages[0] if pages else None,
            'end_page': pages[-1] if pages else None,
            'phrases': segment_info.get('phrases', []),
            'topics': segment_info.get('topics', [])
        }
    }
    
    # 处理 multimodal_contents
    if content_text:
        if multimodal_map_dict:
            # 有多模态映射，处理混合内容
            multimodal_contents = add_multimodal_contents_to_content(content_text, multimodal_map_dict)
        else:
            # 没有多模态映射，将纯文本转为 multimodal_contents 格式
            multimodal_contents = [{"type": "text", "content": content_text}]
        
        if multimodal_contents:
            search_data['multimodal_contents'] = multimodal_contents
    
    # 添加可选的category字段
    #if segment_info.get('category_name'):
    #    search_data['category_name'] = segment_info['category_name']
    #if segment_info.get('category_id'):
    #    search_data['category_id'] = segment_info['category_id']
    if category_id and category_name:
        # 确保 category_id 是字符串类型
        category_id = str(category_id) if not isinstance(category_id, str) else category_id
        category_infos = []
        category_ids = category_id.split(',')
        category_names = category_name.split(',')
        for category_id, category_name in zip(category_ids, category_names):
            category_infos.append({
                'category_id': category_id,
                'category_name': category_name,
                'score': 1.0,
                'source': 'manual'
            })
        search_data['category_infos'] = category_infos
    if task_id:
        search_data['task_id'] = task_id
    return search_data


def trans_html_segment_to_search_data(segment_info: Dict[str, Any], category_id=None, category_name=None, task_id=None, multimodal_map_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    将html片段数据转换为搜索索引格式
    Args:
        segment_info: 文档片段数据，包含content、keywords等字段
                      content为字符串（formatted_text），不是字典
        category_id: 类目ID
        category_name: 类目名称
        task_id: 任务ID
        multimodal_map_dict: 多模态映射字典（可选）
    Returns:
        Dict[str, Any]: 搜索索引格式的数据
    """
    # 获取文件类型
    from_file = segment_info.get('from_file_name', '')
    file_type = 'html'  # 默认为html
    if from_file:
        if from_file.lower().endswith('.pdf'):
            file_type = 'pdf'
        elif from_file.lower().endswith(('.doc', '.docx')):
            file_type = 'doc'
        elif from_file.lower().endswith('.html'):
            file_type = 'html'
    
    # content直接是字符串（formatted_text），不需要转换
    content_text = segment_info.get('content', '')
    if not isinstance(content_text, str):
        # 如果不是字符串，尝试转换为字符串
        content_text = str(content_text) if content_text else ''
    
    # 构建检索文本列表
    indexes = []
    # 添加关键词组合
    if segment_info.get('keywords'):
        keywords = segment_info['keywords']
        if keywords:  # 确保列表不为空
            indexes.append({
                'text': ','.join(keywords) if isinstance(keywords, list) else str(keywords)
            })
    # 添加短语组合
    if segment_info.get('phrases'):
        phrases = segment_info['phrases']
        if phrases and isinstance(phrases, list):
            for phrase in phrases:
                if phrase:  # 确保短语不为空
                    indexes.append({
                        'text': str(phrase)
                    })
    # 添加每个主题
    if segment_info.get('topics'):
        topics = segment_info['topics']
        if topics and isinstance(topics, list):
            for topic in topics:
                if topic:  # 确保主题不为空
                    indexes.append({'text': str(topic)})
    # 添加文件名作为索引
    if segment_info.get('index_file_name'):
        indexes.append({
            'text': segment_info['index_file_name']
        })
    
    # 构建搜索索引数据
    search_data = {
        'content': content_text,  # 文本内容（字符串）
        'data_type': 'segment',  # segment类型
        'platform': segment_info.get('platform', ''),
        'audit_result': -1,  # 默认未审核
        'quality_level': 'high',  # 文档片段默认高等质量
        'from_type': file_type,
        'indexes': indexes,
        'keywords': segment_info.get('keywords', []),
        'ext_info': {
            'from_file_name': segment_info.get('from_file_name', ''),
            'phrases': segment_info.get('phrases', []),
            'topics': segment_info.get('topics', [])
        }
    }
    
    # 处理 multimodal_contents
    if content_text:
        if multimodal_map_dict:
            # 有多模态映射，处理混合内容
            multimodal_contents = add_multimodal_contents_to_content(content_text, multimodal_map_dict)
        else:
            # 没有多模态映射，将纯文本转为 multimodal_contents 格式
            multimodal_contents = [{"type": "text", "content": content_text}]
        
        if multimodal_contents:
            search_data['multimodal_contents'] = multimodal_contents
    
    # segment_info 中已经有了就不需要再添加了
    category_id_segment_info = segment_info.get('category_id', '')
    category_name_segment_info = segment_info.get('category_name', '')
    category_id = category_id_segment_info if category_id_segment_info else category_id
    category_name = category_name_segment_info if category_name_segment_info else category_name
    # 添加类目信息（如果存在）
    if category_id and category_name:
        # 确保 category_id 是字符串类型
        category_id = str(category_id) if not isinstance(category_id, str) else category_id
        category_infos = []
        category_ids = category_id.split(',')
        category_names = category_name.split(',')
        for category_id, category_name in zip(category_ids, category_names):
            category_infos.append({
                'category_id': category_id,
                'category_name': category_name,
                'score': 1.0,
                'source': 'manual'
            })
        search_data['category_infos'] = category_infos
    if task_id:
        search_data['task_id'] = task_id
    
    return search_data

def trans_segment_to_search_data_for_file(input_file, output_file, field_num=0, category_id=None, category_name=None, task_id=None, multimodal_mapping_path: Optional[str] = None):
    """
    将input_file中的所有文件转换成search_index 中insert所需格式
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        field_num: segment_info所在字段位置
        category_id: 分类ID
        category_name: 分类名称
        task_id: 任务ID
        multimodal_mapping_path: 多模态信息（图片，文件，video）映射文件路径（可选）
    """
    # 加载多模态映射（如果提供了路径）
    multimodal_map_dict = None
    if multimodal_mapping_path:
        multimodal_map_dict = _load_multimodal_mapping(multimodal_mapping_path)
        logging.info(f'加载多模态映射: {multimodal_mapping_path}, 映射数量: {len(multimodal_map_dict)}')
    
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as of:
        for line in f:
            columns = line.strip().split('\t')
            
            if len(columns) > field_num:
                segment_info = json.loads(columns[field_num])
                search_data = trans_doc_segment_to_search_data(segment_info, category_id, category_name, task_id, multimodal_map_dict)
                of.write(json.dumps(search_data, ensure_ascii=False) + '\n')

def trans_html_segment_to_search_data_for_file(input_file, output_file, field_num=0, category_id=None, category_name=None, task_id=None, multimodal_mapping_path: Optional[str] = None):
    """
    将input_file中的所有文件转换成search_index 中insert所需格式
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
        field_num: segment_info所在字段位置
        category_id: 分类ID
        category_name: 分类名称
        task_id: 任务ID
        multimodal_mapping_path: 多模态信息（图片，文件，video）映射文件路径（可选）
    """
    # 加载多模态映射（如果提供了路径）
    multimodal_map_dict = None
    if multimodal_mapping_path:
        multimodal_map_dict = _load_multimodal_mapping(multimodal_mapping_path)
        logging.info(f'加载多模态映射: {multimodal_mapping_path}, 映射数量: {len(multimodal_map_dict)}')
    
    with open(input_file, 'r', encoding='utf-8') as f, open(output_file, 'w', encoding='utf-8') as of:
        for line in f:
            columns = line.strip().split('\t')
            if len(columns) > field_num:
                segment_info = json.loads(columns[field_num])
                search_data = trans_html_segment_to_search_data(segment_info, category_id, category_name, task_id, multimodal_map_dict)
                of.write(json.dumps(search_data, ensure_ascii=False) + '\n')



def trans_review_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]] = None, image_save_dir: str = None):
    """
    将审核后的excel文件转换为JSON格式文件
    """
    try:
        # 处理list_field_names参数
        if isinstance(list_field_names, str):
            list_field_names = [name.strip() for name in list_field_names.split(',') if name.strip()]
        
        wb = load_workbook(excel_file, read_only=False, data_only=True)
        excel_base_name = os.path.basename(excel_file)
        excel_name = os.path.splitext(excel_base_name)[0]
        
        # 如果指定了图片保存目录，确保目录存在
        if image_save_dir:
            os.makedirs(image_save_dir, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                # 获取表头（第一行作为key）
                headers = [cell.value for cell in next(ws.rows) if cell.value is not None]
                column_mapping = map_excel_columns(headers)
                canonical_by_idx = {idx: field for field, idx in column_mapping.items()} if column_mapping else {}
                logging.info(f"表头: {headers}")
                
                # 获取所有图片及其位置
                image_map = {}
                for image in ws._images:
                    logging.info(f"Found image: {image}")
                    if not hasattr(image, 'anchor'):
                        continue
                    
                    try:
                        # 获取图片位置
                        row = image.anchor._from.row + 1
                        col = image.anchor._from.col + 1
                        logging.info(f"Image position: row={row}, col={col}")
                        
                        # 尝试获取图片数据
                        if hasattr(image, '_data'):
                            img_data = image._data()
                        elif hasattr(image, 'ref') and hasattr(image.ref, 'image'):
                            if hasattr(image.ref.image, 'blob'):
                                img_data = image.ref.image.blob
                            elif hasattr(image.ref.image, '_data'):
                                img_data = image.ref.image._data()
                            else:
                                logging.warning(f"Cannot get image data from {image}")
                                continue
                        else:
                            logging.warning(f"Cannot get image data from {image}")
                            continue
                            
                        # 验证图片数据
                        try:
                            img = Image.open(io.BytesIO(img_data))
                            # 如果能打开图片，说明数据是有效的
                            if (row, col) not in image_map:
                                image_map[(row, col)] = []
                            image_map[(row, col)].append((img_data, img.format.lower() if img.format else 'png'))
                        except Exception as e:
                            logging.error(f"Invalid image data: {str(e)}")
                            continue
                            
                    except Exception as e:
                        logging.error(f"Error processing image: {str(e)}")
                        continue
                
                # 遍历数据行
                for row_idx, row in enumerate(list(ws.rows)[1:], 2):  # 从2开始，因为1是表头
                    row_data = {}
                    ext_info = {
                        'from_file_name': f'{excel_name}_{sheet_name}'
                    }
                    row_data['ext_info'] = ext_info
                    
                    # 处理每一列的数据
                    for col_idx, (header, cell) in enumerate(zip(headers, row), 1):
                        if cell.value is not None and str(cell.value).strip():  # 只处理非空值
                            field_name = _canonical_excel_field(header, col_idx - 1, canonical_by_idx)
                            field_name_str = str(field_name)
                            if list_field_names and field_name in list_field_names:
                                value_list = [v.strip() for v in str(cell.value).split('|') if v.strip()]
                                row_data[field_name] = value_list
                            elif field_name == 'indexes':
                                text_list = str(cell.value).split('|')
                                text_list = [{"text": t.strip()} for t in text_list if t.strip()]
                                row_data[field_name] = text_list
                            elif field_name_str.find("image_path") != -1:
                                image_path_list = str(cell.value).split('|')
                                row_data.setdefault('ori_image_path', [])
                                row_data['ori_image_path'].extend(image_path_list)
                            elif field_name_str.find("image_data") != -1 and image_save_dir:
                                # 检查该位置是否有图片
                                cell_pos = (row_idx, col_idx)
                                logging.info(f"Checking for image at position {cell_pos}")
                                if cell_pos in image_map:
                                    row_data.setdefault('ori_image_path', [])
                                    for idx, (img_data, img_format) in enumerate(image_map[cell_pos]):
                                        try:
                                            # 构建图片文件名
                                            image_filename = f"{excel_name}_{row_idx}_{col_idx}_{idx}.{img_format}"
                                            image_path = os.path.join(image_save_dir, image_filename)
                                            
                                            # 保存图片数据
                                            with open(image_path, 'wb') as f_img:
                                                f_img.write(img_data)
                                            
                                            # 在JSON中记录图片路径
                                            row_data['ori_image_path'].append(image_path)
                                            logging.info(f"Saved image to {image_path}")
                                        except Exception as e:
                                            tb = traceback.format_exc()
                                            logging.error(f"保存图片失败: {str(e)}")
                                            logging.error(f"tb: {tb}")
                            else:
                                row_data[field_name] = cell.value
                    
                    # 添加 multimodal_contents 字段（纯文本格式）
                    if 'content' in row_data and row_data['content']:
                        row_data['multimodal_contents'] = [
                            {"type": "text", "content": row_data['content']}
                        ]
                    
                    # 写入JSON行
                    if len(row_data) > 1:  # 确保不只有ext_info
                        f.write(json.dumps(row_data, ensure_ascii=False) + '\n')
        
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"转换Excel到JSON时发生错误: {str(e)}")
        raise



def trans_web_excel_to_json_file(excel_file: str, output_file: str, list_field_names: Union[str, List[str]] = None, image_save_dir: str = None, extra_field_name_dict: Dict[str, Any] = None):
    """
    将审核后的excel文件转换为JSON格式文件
    """
    try:
        extra_field_names = ['category_id', 'category_name', 'task_id', 'client', 'file_name', 'dataset', 'data_type', 'from_type', 'from_type_norm', 'audit_result', 'index_name'] # 可以外部传入的
        # 处理list_field_names参数
        if isinstance(list_field_names, str):
            list_field_names = [name.strip() for name in list_field_names.split(',') if name.strip()]
        
        wb = load_workbook(excel_file, read_only=False, data_only=True)
        excel_base_name = os.path.basename(excel_file)
        excel_name = os.path.splitext(excel_base_name)[0]
        
        # 如果指定了图片保存目录，确保目录存在
        if image_save_dir:
            os.makedirs(image_save_dir, exist_ok=True)
        
        # 获取类目映射（用于补全category_name和category_id）
        name_to_id_map = {}
        id_to_name_map = {}
        if extra_field_name_dict and extra_field_name_dict.get('client'):
            try:
                from category_sys_manager.category_sys_util import get_category_maps
                name_to_id_map, id_to_name_map = get_category_maps(extra_field_name_dict.get('client'))
                if name_to_id_map:
                    logging.info(f"成功获取客户端 {extra_field_name_dict.get('client')} 的类目映射，共 {len(name_to_id_map)} 个类目")
            except Exception as e:
                logging.warning(f"获取类目映射失败: {e}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                # 获取表头（第一行作为key）
                headers = [cell.value for cell in next(ws.rows) if cell.value is not None]
                column_mapping = map_excel_columns(headers)
                canonical_by_idx = {idx: field for field, idx in column_mapping.items()} if column_mapping else {}
                logging.info(f"表头: {headers}")
                
                # 获取所有图片及其位置
                image_map = {}
                for image in ws._images:
                    logging.info(f"Found image: {image}")
                    if not hasattr(image, 'anchor'):
                        continue
                    
                    try:
                        # 获取图片位置
                        row = image.anchor._from.row + 1
                        col = image.anchor._from.col + 1
                        logging.info(f"Image position: row={row}, col={col}")
                        
                        # 尝试获取图片数据
                        if hasattr(image, '_data'):
                            img_data = image._data()
                        elif hasattr(image, 'ref') and hasattr(image.ref, 'image'):
                            if hasattr(image.ref.image, 'blob'):
                                img_data = image.ref.image.blob
                            elif hasattr(image.ref.image, '_data'):
                                img_data = image.ref.image._data()
                            else:
                                logging.warning(f"Cannot get image data from {image}")
                                continue
                        else:
                            logging.warning(f"Cannot get image data from {image}")
                            continue
                            
                        # 验证图片数据
                        try:
                            img = Image.open(io.BytesIO(img_data))
                            # 如果能打开图片，说明数据是有效的
                            if (row, col) not in image_map:
                                image_map[(row, col)] = []
                            image_map[(row, col)].append((img_data, img.format.lower() if img.format else 'png'))
                        except Exception as e:
                            logging.error(f"Invalid image data: {str(e)}")
                            continue
                            
                    except Exception as e:
                        logging.error(f"Error processing image: {str(e)}")
                        continue
                
                # 遍历数据行
                for row_idx, row in enumerate(list(ws.rows)[1:], 2):  # 从2开始，因为1是表头
                    row_data = {}
                    ext_info = {
                        'from_file_name': f'{excel_name}_{sheet_name}'
                    }
                    row_data['ext_info'] = ext_info
                    
                    # 处理每一列的数据
                    for col_idx, (header, cell) in enumerate(zip(headers, row), 1):
                        if cell.value is not None and str(cell.value).strip():  # 只处理非空值
                            field_name = _canonical_excel_field(header, col_idx - 1, canonical_by_idx)
                            field_name_str = str(field_name)
                            header_str = str(header)
                            if list_field_names and field_name in list_field_names:
                                value_list = [v.strip() for v in str(cell.value).split('|') if v.strip()]
                                row_data[field_name] = value_list
                            elif field_name == 'indexes':
                                text_list = str(cell.value).split('|')
                                text_list = [{"text": t.strip()} for t in text_list if t.strip()]
                                row_data[field_name] = text_list
                            elif field_name_str.find("image_path") != -1:
                                image_path_list = str(cell.value).split('|')
                                row_data.setdefault('ori_image_path', [])
                                row_data['ori_image_path'].extend(image_path_list)
                            elif field_name == 'title' or header_str.find("Question") != -1:
                                row_data['title'] = cell.value
                            elif field_name == 'content' or header_str.find("Answer") != -1:
                                row_data['content'] = cell.value
                            elif field_name_str.find("image_data") != -1 and image_save_dir:
                                # 检查该位置是否有图片
                                cell_pos = (row_idx, col_idx)
                                logging.info(f"Checking for image at position {cell_pos}")
                                if cell_pos in image_map:
                                    row_data.setdefault('ori_image_path', [])
                                    for idx, (img_data, img_format) in enumerate(image_map[cell_pos]):
                                        try:
                                            # 构建图片文件名
                                            image_filename = f"{excel_name}_{row_idx}_{col_idx}_{idx}.{img_format}"
                                            image_path = os.path.join(image_save_dir, image_filename)
                                            
                                            # 保存图片数据
                                            with open(image_path, 'wb') as f_img:
                                                f_img.write(img_data)
                                            
                                            # 在JSON中记录图片路径
                                            row_data['ori_image_path'].append(image_path)
                                            logging.info(f"Saved image to {image_path}")
                                        except Exception as e:
                                            tb = traceback.format_exc()
                                            logging.error(f"保存图片失败: {str(e)}")
                                            logging.error(f"tb: {tb}")
                            else:
                                row_data[field_name] = cell.value
                    if len(row_data) <= 1: # 什么数据都没有, 只有ext_info
                        continue

                    if name_to_id_map or id_to_name_map:
                        cat_name = row_data.get('category_name')
                        cat_id = row_data.get('category_id')
                        if cat_name and not cat_id and cat_name in name_to_id_map:
                            row_data['category_id'] = name_to_id_map[cat_name]
                        elif cat_id and not cat_name and str(cat_id) in id_to_name_map:
                            row_data['category_name'] = id_to_name_map[str(cat_id)]
                        
                    for extra_field_name in extra_field_names:
                        if extra_field_name not in row_data and extra_field_name_dict.get(extra_field_name):
                            row_data[extra_field_name] = extra_field_name_dict.get(extra_field_name)
                    if not row_data.get('data_type'):
                        if 'title' in row_data:
                            row_data['data_type'] = 'qa'
                        else:
                            row_data['data_type'] = 'segment'
                    
                    # 补全类目信息（在转换成category_infos之前）

                            
                    if 'category_id' in row_data and 'category_name' in row_data:
                        row_data['category_infos'] = [{
                            'category_id': row_data['category_id'],
                            'category_name': row_data['category_name'],
                            'score': 1.0,
                            'source': 'manual'
                        }]
                    if 'category_id' in row_data:
                        del row_data['category_id']
                    if 'category_name' in row_data:
                        del row_data['category_name']
                    
                    # 添加 multimodal_contents 字段（纯文本格式）
                    if 'content' in row_data and row_data['content']:
                        row_data['multimodal_contents'] = [
                            {"type": "text", "content": row_data['content']}
                        ]
                    if 'from_type' not in row_data:
                        row_data['from_type'] = "manual"
                    
                    # 写入JSON行
                      # 确保不只有ext_info
                    f.write(json.dumps(row_data, ensure_ascii=False) + '\n')
        
    except Exception as e:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error(f"转换Excel到JSON时发生错误: {str(e)}")
        raise


def trans_es_data_to_excel(es_data_file: str, output_file: str, headers=None, is_need_trans_column=False):
    """
    将ES数据转换为Excel文件
    
    Args:
        es_data_file (str): ES数据文件路径,每行为一个JSON格式的数据
        output_file (str): 输出的Excel文件路径
    """
    try:
        # 创建新的工作簿
        wb = Workbook()
        ws = wb.active
        
        # 写入表头
        if headers is None:
            headers = ['_id', 'title', 'content', 'synonyms_title', 'supply_info_query', 
                  'platform', 'data_type', 'from_type', 'audit_result', 'quality_level', 'from_chat_history']
        elif isinstance(headers, (list, tuple)):  # list 之前会掉进下面的 else 报错
            headers = list(headers)
        elif isinstance(headers, str):
            headers = headers.split(',')
        else:
            raise ValueError(f"headers参数类型错误: {type(headers)}")
        if isinstance(is_need_trans_column, str):
            is_need_trans_column = is_need_trans_column.lower() == 'true'
        if is_need_trans_column: # 保证是否已经上线在最后
            if '是否已经上线'in headers:
                headers.remove('是否已经上线')
            headers.append('是否已经上线')
        ws.append(headers)
        
        # 读取并处理每行数据
        with open(es_data_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 解析JSON数据
                    data = json.loads(line.strip())
                    
                    # 准备行数据
                    row_data = []
                    for header in headers:
                        if header == 'synonyms_title':
                            row_data.append('|'.join(data.get(header, [])))
                        else:
                            row_data.append(data.get(header, ''))
                    if is_need_trans_column:
                        is_audit = data.get('audit_result', -1)
                        quality_level = data.get('quality_level', '')
                        if is_audit != 0 and quality_level == 'high':
                            row_data.append('是')
                        elif is_audit == 1:
                            row_data.append('是')
                        else:
                            row_data.append('否')
                    # 写入行数据
                    ws.append(row_data)
                    
                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析错误: {str(e)}, 行内容: {line}")
                    continue
                except Exception as e:
                    logging.error(f"处理数据行时发生错误: {str(e)}, 行内容: {line}")
                    continue
        
        # 调整列宽
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 100)  # 限制最大宽度为100
            ws.column_dimensions[column_letter].width = adjusted_width
            
        # 保存Excel文件
        wb.save(output_file)
        logging.info(f"Excel文件已保存到: {output_file}")
        
    except Exception as e:
        logging.error(f"转换ES数据到Excel时发生错误: {str(e)}")
        raise



def trans_es_modify_data_to_excel(es_data_file: str, output_file: str, headers=None):
    """
    将ES数据转换为Excel文件
    
    Args:
        es_data_file (str): ES数据文件路径,每行为一个JSON格式的数据
        output_file (str): 输出的Excel文件路径
        仅过滤is_modify为True的数据
    """
    try:
        # 创建新的工作簿
        wb = Workbook()
        ws = wb.active
        
        # 写入表头
        if headers is None:
            headers = ['_id', 'title', 'new_content', 'old_content', 'synonyms_title', 'supply_info_query', 
                  'platform', 'data_type', 'from_type', 'need_modify', 'quality_level']
        elif isinstance(headers, tuple):
            headers = list(headers)
        elif isinstance(headers, str):
            headers = headers.split(',')
        else:
            raise ValueError(f"headers参数类型错误: {type(headers)}")

        ws.append(headers)
        
        # 读取并处理每行数据
        with open(es_data_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 解析JSON数据
                    data = json.loads(line.strip())
                    if not data.get('is_modify', False):
                        continue

                    # 准备行数据
                    row_data = []
                    for header in headers:
                        if header == 'new_content':
                            row_data.append(data.get('modify_content', ''))
                        elif header == 'old_content':
                            row_data.append(data.get('content', ''))
                        elif header == 'need_modify':
                            row_data.append(int(data.get('is_modify', False)))
                        elif header == 'synonyms_title':
                            row_data.append('|'.join(data.get(header, [])))
                        else:
                            row_data.append(data.get(header, ''))
                    
                    # 写入行数据
                    ws.append(row_data)
                    
                except json.JSONDecodeError as e:
                    logging.error(f"JSON解析错误: {str(e)}, 行内容: {line}")
                    continue
                except Exception as e:
                    logging.error(f"处理数据行时发生错误: {str(e)}, 行内容: {line}")
                    continue
        
        # 调整列宽
        for column in ws.columns:
            max_length = 0
            column_letter = get_column_letter(column[0].column)
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 100)  # 限制最大宽度为100
            ws.column_dimensions[column_letter].width = adjusted_width
            
        # 保存Excel文件
        wb.save(output_file)
        logging.info(f"Excel文件已保存到: {output_file}")
        
    except Exception as e:
        logging.error(f"转换ES数据到Excel时发生错误: {str(e)}")
        raise

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'batch_json_to_excel': batch_json_to_excel,
        'output_qa_json_trans_result': output_qa_json_trans_result,
        'output_page_content_trans_result': output_page_content_trans_result,
        'batch_split_json_quality_to_excel': batch_split_json_quality_to_excel,
        'batch_trans_qa_to_search_data': batch_trans_qa_to_search_data,
        'batch_select_high_quality_qa_to_json': batch_select_high_quality_qa_to_json,
        'excel_to_qa_json': excel_to_qa_json,
        'batch_select_high_quality_qa_and_white_answer_to_json': batch_select_high_quality_qa_and_white_answer_to_json,
        'trans_segment_to_search_data_for_file': trans_segment_to_search_data_for_file,
        'trans_html_segment_to_search_data_for_file': trans_html_segment_to_search_data_for_file,
        'trans_review_excel_to_json_file': trans_review_excel_to_json_file,
        'trans_web_excel_to_json_file': trans_web_excel_to_json_file,
        'classify_excel_upload': classify_excel_upload,
        'trans_es_data_to_excel': trans_es_data_to_excel,
        'trans_qa_to_search_data_one_file': trans_qa_to_search_data_one_file,
        'trans_es_modify_data_to_excel': trans_es_modify_data_to_excel,
    })
    
