from datetime import datetime
from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
from kdb.retrieval.ingestion.identifiers import gen_data_id
import logging

def test_insert_letian_excel(data_file: str, config_path: str):
    """
    测试插入乐天Excel数据
    Args:
        data_file: 数据文件路径
        config_path: 配置文件路径
    """
    import json
    import logging
    from datetime import datetime
    from kdb.retrieval.ingestion.raw_records import LocalRawDataInterface
    logging.info(f'process data file: {data_file}')
    # 初始化SearchDataInterface
    logging.info(f"初始化SearchDataInterface, index_name: letian, config_path: {config_path}")
    search_interface = SearchDataInterface(config_path=config_path, index_name='RakutenFrance')

    # 读取数据文件
    rawdata_interface = LocalRawDataInterface(data_file)
    for data in rawdata_interface.read_data():
        # 转换数据格式
        #raw_data = json.loads(data)
        raw_data = data

        # 转换数据格式
        insert_data = {
            'title': raw_data['question'],  # 使用question作为title
            'content': raw_data['answer'],  # 使用answer作为content
            'synonyms_title': raw_data.get('synonyms_query', []),  # 同义问题作为synonyms_title
            'data_type': 'qa',  # 问答类型数据
            'platform': 'RakutenFrance',  # 平台为乐天
            'audit_result': 1,  # 默认未审核
            'quality_level': 'high',  # 默认中等质量
            'from_type': 'excel',  # 来源为excel
            'insert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'ext_info': {}  # 额外信息
        }
        for key, value in raw_data.items():
            if key not in insert_data:
                insert_data['ext_info'][key] = value

        # 生成_id
        insert_data['_id'] = gen_data_id(insert_data)

        # 插入数据
        try:
            success, message = search_interface.insert_data(insert_data)
            if success:
                logging.info(f"成功插入数据: {insert_data['_id']}")
            else:
                logging.error(f"插入数据失败: {insert_data['_id']}, message: {message}")
        except Exception as e:
            logging.error(f"插入数据异常: {str(e)}")
            raise


def test_search_by_query(query: str, config_path: str):
    """
    测试根据query搜索数据
    Args:
        query: 查询文本
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name='mix')
    index_names = 'rakutenfrance'
    results = search_interface.search_data_by_query(query, index_names=index_names, size=10)
    for result in results:
        logging.info(f"搜索结果: {result}")


def test_insert(index_names:str, config_path:str):
    """
    """
    search_interface = SearchDataInterface(config_path=config_path, index_name=index_names)
    insert_data = {
        'title': 'test',
        'content': 'content',
        'data_type': 'qa',
        'from_type': 'chat',
        'insert_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'ext_info':  {}
    }
    success, message = search_interface.insert_data(insert_data)
    logging.info(f"插入数据: {insert_data}, 成功: {success}, 消息: {message}")
