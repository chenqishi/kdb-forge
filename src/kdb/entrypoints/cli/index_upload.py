from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
import os
import time

def insert_data_to_search_index(data_file: str, config_path: str, use_platform_index: bool = True,
                                index_name_assign: str = None, data_type=None, platform=None, from_type=None,
                                is_update_data: bool = False,
                                is_only_title: bool = False,
                                basic_threshold: float = 0.7,
                                title_basic_threshold: float = 0.95,
                                check_duplicate: bool = None,
                                is_need_llm: bool = None,
                                allowed_quality_levels=None,
                                required_review_decision: str = None,
                                result_file: str = None,
                                ):
    """
    批量插入search_index数据
    Args:
        data_file: 数据文件路径
        config_path: 配置文件路径
        check_duplicate: 是否做入库查重。None 表示沿用配置文件里的 check_duplicate；
            传 False 可关闭查重，用于「已在外部确认过不重复、且默认查重会误杀」的补插场景
            （例如无 title 的 segment：判重的 min(title_sim, content_sim) 恒为 -1，
             数值规则永不触发，结果全部由主题级 LLM 决定，会把同一篇文档的不同页判成重复）
        is_need_llm: 是否在向量规则无法确定时调用 LLM 精判。None 沿用索引配置；False
            保留向量查重，但跳过 LLM 精判，适合外部精判服务限流时的任务级降级。
        allowed_quality_levels: 可入库的质量等级，字符串时用逗号分隔。None 保持旧行为。
        required_review_decision: 要求的审核决策，None 保持旧行为。
        result_file: 可选的 JSON 统计文件，用于返回真实入库/查重/闸门数量。
    """
    import json
    import logging
    from datetime import datetime
    from kdb.retrieval.ingestion.raw_records import LocalRawDataInterface
    logging.info(f'process data file: {data_file}')
    # 初始化SearchDataInterface
    logging.info(f"初始化SearchDataInterface, index_name: letian, config_path: {config_path}")
    search_interface = SearchDataInterface(config_path=config_path, index_name='mix')
    if isinstance(is_only_title, str):
        is_only_title = is_only_title.lower() == 'true'
    if isinstance(check_duplicate, str):
        check_duplicate = check_duplicate.lower() == 'true'
    if isinstance(is_need_llm, str):
        is_need_llm = is_need_llm.lower() == 'true'
    if check_duplicate is False:
        logging.warning('已关闭入库查重（check_duplicate=False），请确认待插数据已在外部去重')
    if isinstance(allowed_quality_levels, str):
        allowed_quality_levels = {
            value.strip().lower() for value in allowed_quality_levels.split(',') if value.strip()
        }
    elif allowed_quality_levels:
        allowed_quality_levels = {
            str(value).strip().lower() for value in allowed_quality_levels if str(value).strip()
        }
    required_review_decision = str(required_review_decision or '').strip().lower() or None

    result_stats = {
        'input_num': 0,
        'gate_skip_num': 0,
        'quality_gate_skip_num': 0,
        'review_gate_skip_num': 0,
        'tagged_duplicate_skip_num': 0,
        'insert_attempt_num': 0,
        'insert_success_num': 0,
        'duplicate_skip_num': 0,
        'insert_failure_num': 0,
    }

    def _write_result_file():
        if not result_file:
            return
        result_dir = os.path.dirname(result_file)
        if result_dir:
            os.makedirs(result_dir, exist_ok=True)
        temp_file = result_file + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(result_stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_file, result_file)

    # 读取数据文件
    rawdata_interface = LocalRawDataInterface(data_file)
    index_num = 0
    whole_start_time = time.time()
    for data in rawdata_interface.read_data(is_need_id=False):
        # 转换数据格式
        logging.info(f"start read data, data_id: {data.get('_id')}")
        #raw_data = json.loads(data)
        index_num += 1
        result_stats['input_num'] += 1
        quality_level = str(data.get('quality_level') or '').strip().lower()
        review_decision = str(
            data.get('review_decision') or data.get('ext_info', {}).get('review_decision') or ''
        ).strip().lower()
        if allowed_quality_levels and quality_level not in allowed_quality_levels:
            result_stats['gate_skip_num'] += 1
            result_stats['quality_gate_skip_num'] += 1
            logging.info("质量闸门跳过 title:%s quality_level:%s", data.get('title'), quality_level)
            continue
        if required_review_decision and review_decision != required_review_decision:
            result_stats['gate_skip_num'] += 1
            result_stats['review_gate_skip_num'] += 1
            logging.info("审核闸门跳过 title:%s review_decision:%s", data.get('title'), review_decision)
            continue
        quality_info = data.get('ext_info', {}).get('quality_info', [])
        quality_info_str = '|'.join(quality_info)
        if '重复' in quality_info_str:
            result_stats['tagged_duplicate_skip_num'] += 1
            logging.info(f"数据重复 title:{data.get('title')}，content:{data.get('content')}，跳过插入")
            continue
        # 转换数据格式
        insert_data = data

        # 生成_id
        #if '_id' not in insert_data:
        #    insert_data['_id'] = gen_data_id(insert_data)
        if not insert_data.get('platform') and insert_data.get('client'): # 原先业务用在电商所以客户就是平台，这里进行一定兼容，适配后面非电商类数据
            insert_data['platform'] = insert_data.get('client')
        if index_name_assign:
            index_name = index_name_assign
        elif use_platform_index:
            index_name = insert_data.get('platform')
        else:
            index_name = None
        if 'data_type' not in insert_data and data_type:
            insert_data['data_type'] = data_type
        if 'platform' not in insert_data and platform:
            insert_data['platform'] = platform
        if 'from_type' not in insert_data and from_type:
            insert_data['from_type'] = from_type
        one_data_start_time = time.time()
        # 插入数据
        try:
            result_stats['insert_attempt_num'] += 1
            success, message = search_interface.insert_data(insert_data, index_name=index_name,
                                                            check_duplicate=check_duplicate,
                                                            is_need_llm=is_need_llm,
                                                            is_update_data=is_update_data,
                                                            is_only_title=is_only_title,
                                                            basic_threshold=basic_threshold,
                                                            title_basic_threshold=title_basic_threshold)
            if success:
                result_stats['insert_success_num'] += 1
                logging.info(f"成功插入数据: {insert_data['_id']}")
            elif message == '数据重复':
                result_stats['duplicate_skip_num'] += 1
                logging.info(f"查重跳过数据: {insert_data['_id']}")
            else:
                result_stats['insert_failure_num'] += 1
                logging.error(f"插入数据失败: {insert_data['_id']}, message: {message}")
            one_data_end_time = time.time()
            logging.info(f"插入数据{index_num}条，耗时: {one_data_end_time - one_data_start_time}秒, 总耗时: {one_data_end_time - whole_start_time}秒")
        except Exception as e:
            result_stats['insert_failure_num'] += 1
            _write_result_file()
            logging.error(f"插入数据异常: {str(e)}")
            raise
    _write_result_file()
    logging.info('入库统计: %s', result_stats)
    return result_stats
