from kdb.mining.common.schema.multimodal import _load_multimodal_mapping
from kdb.mining.common.schema.multimodal import add_multimodal_contents_to_content
from typing import Any
from typing import Dict
from typing import Optional
import json
import logging
import traceback

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
