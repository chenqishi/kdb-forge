from kdb.mining.common.schema.document_content import trans_page_content_to_text
from kdb.mining.common.schema.multimodal import _load_multimodal_mapping
from kdb.mining.common.schema.multimodal import add_multimodal_contents_to_content
from typing import Any
from typing import Dict
from typing import Optional
import json
import logging

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
