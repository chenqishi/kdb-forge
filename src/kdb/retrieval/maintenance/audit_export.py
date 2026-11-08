from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
import json
import logging

def gen_audit_data(index_name: str, config_path: str, audit_result: str, quality_level: str = None, from_type: str = None):
    """
    检索所有data_type为qa且audit_result符合条件的数据，并输出到标准输出
    Args:
        index_name: 索引名称
        config_path: 配置文件路径
        audit_result: 审核结果，可以是单个值或逗号分隔的字符串
    """
    # 处理audit_result参数
    if isinstance(audit_result, str):
        audit_result = [int(result) for result in audit_result.split(',')]
    elif isinstance(audit_result, int):
        audit_result = [audit_result]
    else:
        audit_result = list(audit_result)

    if quality_level and  isinstance(quality_level, str) and quality_level != 'all':
        quality_level = quality_level.split(',')
    if quality_level and isinstance(quality_level, tuple):
        quality_level = list(quality_level)
    if from_type and isinstance(from_type, str) and from_type != 'all':
        from_type = from_type.split(',')
    if from_type and isinstance(from_type, tuple):
        from_type = list(from_type)
    # 初始化搜索接口
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_name)

    # 构建简单的bool查询，直接使用ES原生查询格式
    query = {
        "attribute": {
            "audit_result": audit_result,
            "data_type": "qa"
        }
    }
    if quality_level and quality_level != 'all':
        query['attribute']['quality_level'] = quality_level
    if from_type and from_type != 'all':
        query['attribute']['from_type'] = from_type
    try:
        # 使用scroll API进行分批查询，设置较大的batch_size减少请求次数
        for data in search_interface.engine.scroll_search(
            query,  # 包装在query字段中
            batch_size=5000,  # 增大批次大小
            scroll_timeout='10m'  # 增加scroll超时时间
        ):
            print(json.dumps(data, ensure_ascii=False))

    except Exception as e:
        logging.error(f"生成审核数据失败: {str(e)}")


def search_for_audit_data(index_name: str, config_path: str, query_file: str, audit_result: str, quality_level: str = None, from_type: str = None, score_threshold: float = 0.5):
    """
    检索所有data_type为qa且audit_result符合条件的数据，并输出到标准输出
    Args:
        index_name: 索引名称
        config_path: 配置文件路径
        audit_result: 审核结果，可以是单个值或逗号分隔的字符串
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_name)
    if isinstance(audit_result, str):
        audit_result = [int(result) for result in audit_result.split(',')]
    elif isinstance(audit_result, int):
        audit_result = [audit_result]
    else:
        audit_result = list(audit_result)

    if quality_level and  isinstance(quality_level, str) and quality_level != 'all':
        quality_level = quality_level.split(',')
    if quality_level and isinstance(quality_level, tuple):
        quality_level = list(quality_level)
    if from_type and isinstance(from_type, str) and from_type != 'all':
        from_type = from_type.split(',')
    if from_type and isinstance(from_type, tuple):
        from_type = list(from_type)
    attribute_dict = {
        "audit_result": audit_result,
        "data_type": "qa"
    }
    if quality_level and quality_level != 'all':
        attribute_dict['quality_level'] = quality_level
    if from_type and from_type != 'all':
        attribute_dict['from_type'] = from_type
    with open(query_file, 'r') as f:
        for line in f:
            query_text = line.strip()
            results, total_num = search_interface.search_data_by_query(query_text, index_names=index_name, condition_dicts=[attribute_dict], size=10)
            for result in results:
                score = result['similarity']
                if score < score_threshold:
                    continue
                result['search_query'] = query_text
                print(json.dumps(result, ensure_ascii=False))
