import sys
import logging

from datetime import datetime
from collections import defaultdict

from kdb.shared.clients.mysql_connector import MySQLConnector
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.config.legacy_config import GLOBAL_CONFIG


def run_llm_static_batch(task_type, sql_config):
    """
    运行LLM统计批处理任务
    :param task_type: 任务类型，如 daily_report/weekly_report
    :param sql_config: 数据库配置文件路径
    """
    # 1. 从数据库读取配置
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 获取指定task_type的所有配置
        cursor.execute(
            """
            SELECT client, item_key, item_value 
            FROM rf_app_offline_task 
            WHERE task_type = %s
            """,
            (task_type,)
        )
        rows = cursor.fetchall()
        
        # 组织配置数据：client_name -> {item_key: item_value}
        client_configs = defaultdict(dict)
        default_config = {}
        
        for row in rows:
            client = row['client']
            item_key = row['item_key']
            item_value = row['item_value']
            
            if client == 'default':
                default_config[item_key] = item_value
            else:
                client_configs[client][item_key] = item_value
        
    finally:
        connector.close_connection(conn, cursor)
    
    logging.info(f"client_configs: {client_configs}, default_config: {default_config}")
    # 2. 处理每个client的统计任务
    for client_name, config in client_configs.items():
        # 跳过default和enable为0的
        if client_name == 'default':
            continue
            
        enable = config.get('enable', default_config.get('enable', '1'))
        if enable == '0':
            logging.info(f"跳过客户端 {client_name}，enable=0")
            continue
            
        # 合并配置（client配置优先，default兜底）
        merged_config = {}
        config_keys = ['send_url', 'receiver', 'is_group', 'prompt', 'is_id', 'query', 'api_key', 'dify_base_url', 'system_prompt']
        for key in config_keys:
            if key in config:
                merged_config[key] = config[key]
            elif key in default_config:
                merged_config[key] = default_config[key]
        logging.info(f"client_name: {client_name}, merged_config: {merged_config}")
        # 检查必需的api_key
        if 'api_key' not in merged_config:
            logging.warning(f"客户端 {client_name} 缺少api_key配置，跳过")
            continue
            
        # 准备DifyWorkFlowRequest的输入
        dify_inputs = {}
        input_keys = ['send_url', 'receiver', 'is_group', 'prompt', 'is_id', 'query']
        for key in input_keys:
            if key in merged_config:
                value = merged_config[key]
                # 对 is_group 和 is_id 转换为整数
                if key in ['is_group', 'is_id']:
                    try:
                        # 处理字符串 '0', '1', 'true', 'false' 等情况
                        if isinstance(value, str):
                            if value.lower() in ['true', '1']:
                                value = 1
                            elif value.lower() in ['false', '0']:
                                value = 0
                            else:
                                value = int(value)
                        else:
                            value = int(bool(value))
                    except (ValueError, TypeError):
                        logging.warning(f"无法转换 {key}={value} 为整数，使用默认值0")
                        value = 0
                dify_inputs[key] = value
        
        # 添加client_name
        dify_inputs['client_name'] = client_name
        
        # 获取dify配置
        dify_base_url = merged_config.get('dify_base_url', GLOBAL_CONFIG['dify_api_base'])
        api_key = merged_config['api_key']
        system_prompt = merged_config.get('system_prompt')
        
        try:
            # 创建DifyWorkFlowRequest并执行
            dify = DifyWorkFlowRequest(api_base=dify_base_url, api_key=api_key, system_prompt=system_prompt)
            
            # 构建主要输入内容
            main_input = merged_config.get('main_input', f"执行{task_type}统计任务")
            
            # 调用dify
            result = dify.request_dify(main_input, other_inputs=dify_inputs)
            
            logging.info(f"客户端 {client_name} 统计任务完成，结果长度: {len(result) if result else 0}")
            print(f"=== {client_name} {task_type} 统计结果 ===")
            print(result if result else "无结果返回")
            print("=" * 50)
            
        except Exception as e:
            logging.error(f"客户端 {client_name} 统计任务执行失败: {str(e)}")
            continue


def run_llm_static_one(task_type, client, sql_config):
    """
    运行指定客户端的LLM统计任务
    :param task_type: 任务类型，如 daily_report/weekly_report
    :param client: 指定的客户端名称
    :param sql_config: 数据库配置文件路径
    """
    # 1. 从数据库读取配置
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 获取指定task_type的所有配置
        cursor.execute(
            """
            SELECT client, item_key, item_value 
            FROM rf_app_offline_task 
            WHERE task_type = %s
            """,
            (task_type,)
        )
        rows = cursor.fetchall()
        
        # 组织配置数据：client_name -> {item_key: item_value}
        client_configs = defaultdict(dict)
        default_config = {}
        
        for row in rows:
            client_name = row['client']
            item_key = row['item_key']
            item_value = row['item_value']
            
            if client_name == 'default':
                default_config[item_key] = item_value
            else:
                client_configs[client_name][item_key] = item_value
        
    finally:
        connector.close_connection(conn, cursor)
    
    # 2. 处理指定的client统计任务
    if client not in client_configs:
        logging.warning(f"指定的客户端 {client} 在配置中不存在")
        return
    
    config = client_configs[client]
    
    # 检查enable状态
    enable = config.get('enable', default_config.get('enable', '1'))
    if enable == '0':
        logging.info(f"客户端 {client} 已禁用，enable=0")
        return
        
    # 合并配置（client配置优先，default兜底）
    merged_config = {}
    config_keys = ['send_url', 'receiver', 'is_group', 'prompt', 'is_id', 'query', 'api_key', 'dify_base_url', 'system_prompt']
    for key in config_keys:
        if key in config:
            merged_config[key] = config[key]
        elif key in default_config:
            merged_config[key] = default_config[key]
    
    # 检查必需的api_key
    if 'api_key' not in merged_config:
        logging.warning(f"客户端 {client} 缺少api_key配置，无法执行")
        return
        
    # 准备DifyWorkFlowRequest的输入
    dify_inputs = {}
    input_keys = ['send_url', 'receiver', 'is_group', 'prompt', 'is_id', 'query']
    for key in input_keys:
        if key in merged_config:
            value = merged_config[key]
            # 对 is_group 和 is_id 转换为整数
            if key in ['is_group', 'is_id']:
                try:
                    # 处理字符串 '0', '1', 'true', 'false' 等情况
                    if isinstance(value, str):
                        if value.lower() in ['true', '1']:
                            value = 1
                        elif value.lower() in ['false', '0']:
                            value = 0
                        else:
                            value = int(value)
                    else:
                        value = int(bool(value))
                except (ValueError, TypeError):
                    logging.warning(f"无法转换 {key}={value} 为整数，使用默认值0")
                    value = 0
            dify_inputs[key] = value
    
    # 添加client_name
    dify_inputs['client_name'] = client
    
    # 获取dify配置
    dify_base_url = merged_config.get('dify_base_url', GLOBAL_CONFIG['dify_api_base'])
    api_key = merged_config['api_key']
    system_prompt = merged_config.get('system_prompt')
    
    try:
        # 创建DifyWorkFlowRequest并执行
        dify = DifyWorkFlowRequest(api_base=dify_base_url, api_key=api_key, system_prompt=system_prompt)
        
        # 构建主要输入内容
        main_input = merged_config.get('main_input', f"执行{task_type}统计任务")
        
        # 调用dify
        result = dify.request_dify(main_input, other_inputs=dify_inputs)
        
        logging.info(f"客户端 {client} 统计任务完成，结果长度: {len(result) if result else 0}")
        print(f"=== {client} {task_type} 统计结果 ===")
        print(result if result else "无结果返回")
        print("=" * 50)
        
    except Exception as e:
        logging.error(f"客户端 {client} 统计任务执行失败: {str(e)}")


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()

    