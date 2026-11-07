from kdb.shared.config.private_values import private_value as _private_value
import logging
from commons.mysql_connector import MySQLConnector
from query_understanding_analysis.query_category import QueryCategoryDify
from query_understanding_analysis import query_norm
from datetime import datetime, timedelta
from query_understanding_analysis import category_mining
import json
import sys
from config_tools.config import GLOBAL_CONFIG


def _ensure_logging():
    """确保至少有一个INFO级别的stderr日志输出。"""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            stream=sys.stderr,
            level=logging.INFO,
            format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
                   '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
        )
    # 无论是否已有handler，强制提升到INFO，避免外部把root设为WARNING导致无输出
    root.setLevel(logging.INFO)
    for h in root.handlers:
        if h.level > logging.INFO:
            h.setLevel(logging.INFO)

def update_chat_history_category(config_path, client, user, dify_base_url, dify_api_key, start_time, end_time, batch_size=50, system_prompt=None, need_cover=False):
    """
    批量获取指定customer、时间范围内的send_content，分类后更新content_category字段
    :param config_path: 数据库配置文件路径
    :param client: customer名
    :param user: 用户名,如lucy等，为None则不区分用户
    :param dify_base_url: dify模型base_url
    :param dify_api_key: dify模型api_key
    :param start_time: 开始时间，字符串（%Y%m%d%H%M%S）或datetime
    :param end_time: 结束时间，字符串（%Y%m%d%H%M%S）或datetime
    :param batch_size: 每批处理条数
    :param system_prompt: 可选，dify系统提示词
    :param need_cover: 是否覆盖已有分类，False时只更新content_category为null的
    """
    # 初始化分类器
    qc = QueryCategoryDify(config_path, client, dify_base_url, dify_api_key, system_prompt=system_prompt)
    connector = MySQLConnector(config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    update_cursor = conn.cursor()
    try:
        # 时间格式化
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(start_time, datetime):
            start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(end_time, datetime):
            end_time = end_time.strftime('%Y-%m-%d %H:%M:%S')
        # 一次性查出所有需要处理的数据
        select_sql = "SELECT id, send_content FROM data_chat_history WHERE customer=%s AND create_time >= %s AND create_time < %s"
        params = [client, start_time, end_time]
        if user:
            select_sql += " AND user=%s"
            params.append(user)
        if not need_cover:
            select_sql += " AND (content_category IS NULL OR content_category = '')"
        #select_sql += " ORDER BY id"
        cursor.execute(select_sql, params)
        rows = cursor.fetchall()
        total = len(rows)
        logging.info(f"{client} {user}总共需要处理{total}条记录")
        # 分批处理
        for offset in range(0, total, batch_size):
            batch = rows[offset:offset+batch_size]
            ids = [row['id'] for row in batch]
            contents = [row['send_content'] or '' for row in batch]
            # 分类
            try:
                categories = qc.batch_query_category(contents)
            except Exception as e:
                logging.error(f"分类失败: {e}")
                categories = [None] * len(contents)
            # 批量更新
            for id_, cate in zip(ids, categories):
                update_sql = "UPDATE data_chat_history SET content_category=%s WHERE id=%s"
                try:
                    update_cursor.execute(update_sql, (cate, id_))
                except Exception as e:
                    logging.error(f"更新id={id_}失败: {e}")
            conn.commit()
            logging.info(f"已处理{min(offset+batch_size, total)}/{total}")
    finally:
        connector.close_connection(conn, cursor)
        try:
            update_cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass

def batch_update_chat_history_category_from_sql(sql_config_path,  start_time, end_time, batch_size=50, need_cover=False, need_category_mining=False, client_white_set=None):
    """
    从rf_app_offline_task表读取所有task_type为content_category的配置，按client、user分组，
    组装参数后调用update_chat_history_category。
    :param sql_config_path: 数据库配置文件路径（用于读取rf_app_offline_task）
    :param start_time: 开始时间
    :param end_time: 结束时间
    :param batch_size: 批处理条数
    :param need_cover: 是否覆盖已有分类
    """
    # 从GLOBAL_CONFIG读取dify默认配置
    default_base_url = GLOBAL_CONFIG['dify_api_base']
    default_api_key = _private_value('ed40fce304a6f6bad5f24581')
    default_system_prompt = None
    if client_white_set:
        client_white_set = set(client_white_set.split(','))

    # 读取rf_app_offline_task配置
    connector = MySQLConnector(sql_config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT client, user, item_key, item_value 
            FROM rf_app_offline_task 
            WHERE task_type='content_category' 
        """)
        rows = cursor.fetchall()
        # 组织成{(client, user): {item_key: item_value}}
        config_dict = {}
        for row in rows:
            client = row['client']
            user = row['user']
            # 处理user为None或空字符串的情况
            if user is None or str(user).strip() == '':
                user_key = None
            else:
                user_key = user
            if client_white_set and client not in client_white_set:
                continue
            item_key = row['item_key']
            item_value = row['item_value']
            key = (client, user_key)
            if key not in config_dict:
                config_dict[key] = {}
            config_dict[key][item_key] = item_value
    finally:
        connector.close_connection(conn, cursor)
    
    if not config_dict:
        logging.info("没有找到需要处理的content_category任务配置")
        return
    
    # 过滤：只保留 enable=1 的任务配置
    enabled_config_dict = {}
    for key, item_map in config_dict.items():
        enable_value = item_map.get('enable')
        # 检查 enable 是否为 1（可能是字符串 '1' 或整数 1）
        if enable_value is not None and str(enable_value).strip() == '1':
            enabled_config_dict[key] = item_map
        else:
            client, user = key
            logging.info(f"跳过未启用的任务配置: client={client}, user={user}, enable={enable_value}")
    
    if not enabled_config_dict:
        logging.info("没有找到启用的content_category任务配置（enable=1）")
        return
    
    # 使用过滤后的配置
    config_dict = enabled_config_dict
    logging.info(f"找到 {len(config_dict)} 个启用的content_category任务配置")

    # 针对每个client, user调用update_chat_history_category
    for (client, user), item_map in config_dict.items():
        if need_category_mining:
            logging.info(f"开始自动挖掘{client} {user} {start_time} {end_time}")
            new_cate_num = category_mining.category_auto_mining_and_update(sql_config_path, client, start_time, end_time)
            logging.info(f"自动挖掘完成，新增{client} {user} {new_cate_num}个类目")
        dify_base_url = item_map.get('dify_base_url', default_base_url)
        dify_api_key = item_map.get('dify_api_key', default_api_key)
        system_prompt = item_map.get('system_prompt', default_system_prompt)
        logging.info(f"开始处理{client} {user} {dify_base_url} {dify_api_key} {system_prompt}, start_time={start_time}, end_time={end_time}, batch_size={batch_size}, need_cover={need_cover}")
        update_chat_history_category(
            config_path=sql_config_path,
            client=client,
            user=user,
            dify_base_url=dify_base_url,
            dify_api_key=dify_api_key,
            start_time=start_time,
            end_time=end_time,
            batch_size=batch_size,
            system_prompt=system_prompt,
            need_cover=need_cover
        )


def get_existing_norm_contents(config_path, client, user=None, connector: MySQLConnector = None, limit_num: int = 20000):
    """
    从数据库中获取已有的归一化content集合（按时间倒序轮询去重，直到获取足够数量）
    :param config_path: 数据库配置文件路径
    :param client: customer名
    :param user: 用户名，为None则获取整个customer的
    :param connector: MySQLConnector 实例，为 None 则新建
    :param limit_num: 限制获取的归一化content数量，默认20000（按最新时间倒序）
    :return: {content: None} 字典，embedding为None等待后续计算
    """
    connector = connector or MySQLConnector(config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 简单查询，按时间倒序排列
        select_sql = """
            SELECT norm_content
            FROM data_chat_history 
            WHERE customer=%s AND norm_content IS NOT NULL AND norm_content != ''
        """
        params = [client]
        if user:
            select_sql += " AND user=%s"
            params.append(user)
        
        select_sql += " ORDER BY create_time DESC"
        
        cursor.execute(select_sql, params)
        
        # 轮询取数据，去重直到达到 limit_num
        existing_dict = {}
        fetched_count = 0
        batch_size = 1000  # 每次fetch的批次大小
        
        while len(existing_dict) < limit_num:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                # 没有更多数据了
                break
            
            fetched_count += len(rows)
            
            for row in rows:
                norm_content = row['norm_content']
                if norm_content and norm_content.strip():
                    content_key = norm_content.strip()
                    if content_key not in existing_dict:
                        existing_dict[content_key] = None  # embedding为None，后续计算
                        
                        # 达到目标数量，提前退出
                        if len(existing_dict) >= limit_num:
                            break
        
        logging.info(f"从数据库获取到 {len(existing_dict)} 个已有归一化content（扫描{fetched_count}行，限制最多{limit_num}条，按时间倒序）")
        return existing_dict
        
    finally:
        connector.close_connection(conn, cursor)


def update_content_norm(config_path, client, user, embedding_config_path, start_time, end_time, 
                      similarity_threshold=0.7, need_cover=False):
    """
    批量获取指定customer、时间范围内的send_content，进行content归一化后更新norm_content字段
    :param config_path: 数据库配置文件路径
    :param client: customer名
    :param user: 用户名，为None则不区分用户
    :param embedding_config_path: embedding配置文件路径
    :param start_time: 开始时间，字符串（%Y%m%d%H%M%S）或datetime
    :param end_time: 结束时间，字符串（%Y%m%d%H%M%S）或datetime
    :param similarity_threshold: 相似度阈值，默认0.7
    :param need_cover: 是否覆盖已有归一化结果
    """
    connector = MySQLConnector(config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    update_cursor = conn.cursor()
    
    try:
        # 时间格式化
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(start_time, datetime):
            start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(end_time, str):
            end_time = datetime.strptime(end_time, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(end_time, datetime):
            end_time = end_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # 查询数据
        select_sql = "SELECT id, send_content FROM data_chat_history WHERE customer=%s AND create_time >= %s AND create_time < %s"
        params = [client, start_time, end_time]
        if user:
            select_sql += " AND user=%s"
            params.append(user)
        if not need_cover:
            select_sql += " AND (norm_content IS NULL OR norm_content = '')"
        
        cursor.execute(select_sql, params)
        rows = cursor.fetchall()
        total = len(rows)
        logging.info(f"{client} {user} 总共需要处理{total}条记录进行content归一化")
        
        if total == 0:
            logging.info(f"{client} {user} 没有需要处理的数据")
            return
        
        # 提取content列表
        id_content_map = {}
        for row in rows:
            if row['send_content'] and row['send_content'].strip():
                id_content_map[row['id']] = row['send_content'].strip()
        
        contents = list(id_content_map.values())
        logging.info(f"有效content数量: {len(contents)}")
        
        # 获取已有的归一化content集合
        existing_dict = get_existing_norm_contents(config_path, client, user)
        
        # 调用归一化函数
        norm_mapping = query_norm.norm_query_by_class(
            existing_query_dict=existing_dict,
            queries_to_classify=contents,
            embedding_config_path=embedding_config_path,
            similarity_threshold=similarity_threshold
        )
        
        # 批量更新数据库
        update_count = 0
        for id_, content in id_content_map.items():
            norm_content = norm_mapping.get(content, content)
            update_sql = "UPDATE data_chat_history SET norm_content=%s WHERE id=%s"
            try:
                update_cursor.execute(update_sql, (norm_content, id_))
                update_count += 1
            except Exception as e:
                logging.error(f"更新id={id_}失败: {e}")
        
        conn.commit()
        logging.info(f"{client} {user} content归一化完成，更新{update_count}/{total}条记录")
        
    finally:
        connector.close_connection(conn, cursor)
        try:
            update_cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass


def batch_update_content_norm_from_sql(sql_config_path, start_time, end_time, 
                                       similarity_threshold=0.7, need_cover=False,
                                       client_white_set=None, progress_step=1000, batch_date_range=10,
                                       limit_num=20000):
    """
    从rf_app_offline_task表读取所有task_type为content_norm的配置，按client、user分组，
    进行content归一化并更新到数据库
    当user='all'时，使用两级归一化（获取整个customer的数据一次，按实际user分组后归一化）
    :param sql_config_path: 数据库配置文件路径
    :param start_time: 开始时间
    :param end_time: 结束时间
    :param similarity_threshold: 相似度阈值，默认0.7
    :param need_cover: 是否覆盖已有归一化结果
    :param client_white_set: 客户白名单，逗号分隔的字符串
    :param limit_num: 获取已有归一化content的最大数量，默认20000
    """
    _ensure_logging()
    # 从GLOBAL_CONFIG读取默认配置
    default_embedding_config = GLOBAL_CONFIG.get('embedding_config_path', 
                                                  'config/config_ali_embedding_default.json')
    
    if client_white_set:
        client_white_set = set(client_white_set.split(','))
    
    # 读取rf_app_offline_task配置
    connector = MySQLConnector(sql_config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT client, user, item_key, item_value 
            FROM rf_app_offline_task 
            WHERE task_type='content_norm' 
        """)
        rows = cursor.fetchall()
        
        # 组织成{(client, user): {item_key: item_value}}
        config_dict = {}
        for row in rows:
            client = row['client']
            user = row['user']
            # 处理user为None或空字符串的情况
            if user is None or str(user).strip() == '':
                user_key = None
            else:
                user_key = user.strip()
            if client_white_set and client not in client_white_set:
                continue
            item_key = row['item_key']
            item_value = row['item_value']
            key = (client, user_key)
            if key not in config_dict:
                config_dict[key] = {}
            config_dict[key][item_key] = item_value
    finally:
        connector.close_connection(conn, cursor)
    
    if not config_dict:
        logging.info("没有找到需要处理的content_norm任务配置")
        return
    
    # 过滤：只保留 enable=1 的任务配置
    enabled_config_dict = {}
    for key, item_map in config_dict.items():
        enable_value = item_map.get('enable')
        # 检查 enable 是否为 1（可能是字符串 '1' 或整数 1）
        if enable_value is not None and str(enable_value).strip() == '1':
            enabled_config_dict[key] = item_map
        else:
            client, user = key
            logging.info(f"跳过未启用的任务配置: client={client}, user={user}, enable={enable_value}")
    
    if not enabled_config_dict:
        logging.info("没有找到启用的content_norm任务配置（enable=1）")
        return
    
    # 使用过滤后的配置
    config_dict = enabled_config_dict
    logging.info(f"找到 {len(config_dict)} 个启用的content_norm任务配置")
    
    # 时间格式化，保留 datetime 便于分片
    if isinstance(start_time, str):
        start_dt = datetime.strptime(start_time, '%Y%m%d%H%M%S')
    elif isinstance(start_time, datetime):
        start_dt = start_time
    elif isinstance(start_time, int):
        start_dt = datetime.strptime(str(start_time), '%Y%m%d%H%M%S')
    else:
        raise ValueError("start_time 必须是字符串(%Y%m%d%H%M%S)/int 或 datetime")

    if isinstance(end_time, str):
        end_dt = datetime.strptime(end_time, '%Y%m%d%H%M%S')
    elif isinstance(end_time, datetime):
        end_dt = end_time
    elif isinstance(end_time, int):
        end_dt = datetime.strptime(str(end_time), '%Y%m%d%H%M%S')
    else:
        raise ValueError("end_time 必须是字符串(%Y%m%d%H%M%S)/int 或 datetime")
    
    # 按client分组处理
    clients_to_process = {}  # {client: [(user, config)]}
    for (client, user), item_map in config_dict.items():
        if client not in clients_to_process:
            clients_to_process[client] = []
        clients_to_process[client].append((user, item_map))
    
    # 共享连接器，避免多次初始化
    shared_connector = MySQLConnector(sql_config_path)

    # 处理每个client
    for client, user_configs in clients_to_process.items():
        # 判断是否需要两级归一化（user='all'）
        use_two_level = any(user == 'all' for user, _ in user_configs)
        
        # 获取配置
        embedding_config_path = default_embedding_config
        fetch_user = None
        for user, item_map in user_configs:
            if use_two_level and user == 'all':
                embedding_config_path = item_map.get('embedding_config_path', default_embedding_config)
                fetch_user = 'all'
                break
            elif not use_two_level and fetch_user is None:
                embedding_config_path = item_map.get('embedding_config_path', default_embedding_config)
                fetch_user = user
        
        logging.info(f"开始处理client={client}, 模式={'两级归一化' if use_two_level else '单级归一化'}, embedding配置={embedding_config_path}")

        # 归一化信息共享字典，避免重复计算 embedding
        shared_query_info_dict = {}

        # 生成时间分片
        time_ranges = _generate_time_ranges(start_dt, end_dt, batch_date_range)
        total_batches = len(time_ranges)

        for batch_idx, (batch_start_str, batch_end_str) in enumerate(time_ranges, 1):
            try:
                logging.info(f"client={client} 开始批次 {batch_idx}/{total_batches}，区间 {batch_start_str} ~ {batch_end_str}")

                # ===== 第1步：获取数据（公用） =====
                id_content_user_map = _fetch_content_data(
                    connector=shared_connector,
                    client=client,
                    user=fetch_user,
                    start_time_formatted=batch_start_str,
                    end_time_formatted=batch_end_str,
                    need_cover=need_cover
                )
                logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 数据获取完成，共 {len(id_content_user_map)} 条")

                if not id_content_user_map:
                    logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 没有需要处理的数据")
                    continue

                # ===== 第2步：归一化 =====
                if use_two_level:
                    norm_content_mapping = _process_two_level_norm(
                        connector=shared_connector,
                        client=client,
                        id_content_user_map=id_content_user_map,
                        embedding_config_path=embedding_config_path,
                        similarity_threshold=similarity_threshold,
                        query_info_dict=shared_query_info_dict,
                        limit_num=limit_num
                    )
                else:
                    norm_content_mapping = _process_single_level_norm(
                        connector=shared_connector,
                        client=client,
                        id_content_user_map=id_content_user_map,
                        user_configs=user_configs,
                        embedding_config_path=embedding_config_path,
                        similarity_threshold=similarity_threshold,
                        query_info_dict=shared_query_info_dict,
                        limit_num=limit_num
                    )
                logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 归一化完成，映射数 {len(norm_content_mapping)}，唯一norm {len(set(norm_content_mapping.values()))}")

                # ===== 第3步：将结果更新回数据库（公用） =====
                _update_norm_content_to_db(
                    connector=shared_connector,
                    client=client,
                    id_content_user_map=id_content_user_map,
                    norm_content_mapping=norm_content_mapping,
                    progress_step=progress_step
                )
            except Exception as e:
                logging.error(f"client={client} 批次 {batch_idx}/{total_batches} 处理失败，跳过。错误: {e}", exc_info=True)
                continue


def _fetch_content_data(connector: MySQLConnector, client, user, start_time_formatted, end_time_formatted, need_cover):
    """
    从数据库获取需要处理的content数据（公用）
    :return: {id: (content, user)} 字典
    """
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 一次性查询该customer的所有需要处理的数据
        select_sql = "SELECT id, send_content, user FROM data_chat_history WHERE customer=%s AND create_time >= %s AND create_time < %s"
        params = [client, start_time_formatted, end_time_formatted]
        if user and user != 'all':
            select_sql += " AND user=%s"
            params.append(user)
        if not need_cover:
            select_sql += " AND (norm_content IS NULL OR norm_content = '')"
        
        cursor.execute(select_sql, params)
        rows = cursor.fetchall()
        
        logging.info(f"client={client} 查询到{len(rows)}条数据")
        
        # 构建id到content、user的映射
        id_content_user_map = {}
        for row in rows:
            if row['send_content'] and row['send_content'].strip():
                content = row['send_content'].strip()
                user = row.get('user') or 'unknown'
                id_content_user_map[row['id']] = (content, user)
        
        logging.info(f"client={client} 有效数据{len(id_content_user_map)}条")
        return id_content_user_map
        
    finally:
        connector.close_connection(conn, cursor)


def _process_two_level_norm(connector: MySQLConnector, client, id_content_user_map, embedding_config_path, similarity_threshold, query_info_dict, limit_num=20000):
    """
    两级归一化处理：按user分组后归一化
    :param limit_num: 获取已有归一化content的最大数量
    :return: {content: norm_content} 映射
    """
    logging.info(f"client={client} 使用两级归一化模式")
    
    # 获取已有的归一化content集合（整个customer的）
    existing_dict = get_existing_norm_contents(None, client, user=None, connector=connector, limit_num=limit_num)
    
    # 按user分组收集content
    user_content_dict = {}  # {user: [content_list]}
    for content, user in id_content_user_map.values():
        if user not in user_content_dict:
            user_content_dict[user] = []
        if content not in user_content_dict[user]:  # 去重
            user_content_dict[user].append(content)
    
    logging.info(f"client={client} 按user分组: {dict((k, len(v)) for k, v in user_content_dict.items())}")
    
    # 调用两级归一化
    norm_mapping = query_norm.norm_query_by_user(
        user_query_dict=user_content_dict,
        embedding_config_path=embedding_config_path,
        similarity_threshold=similarity_threshold,
        existing_query_dict=existing_dict,
        query_info_dict=query_info_dict
    )
    
    logging.info(f"client={client} 两级归一化完成，共{len(norm_mapping)}个映射，归一到{len(set(norm_mapping.values()))}个content")
    return norm_mapping


def _process_single_level_norm(connector: MySQLConnector, client, id_content_user_map, user_configs, embedding_config_path, similarity_threshold, query_info_dict, limit_num=20000):
    """
    单级归一化处理：按指定user单独归一化
    :param limit_num: 获取已有归一化content的最大数量
    :return: {content: norm_content} 映射
    """
    logging.info(f"client={client} 使用单级归一化模式")
    
    # 收集所有唯一的content
    all_contents = list(set(content for content, user in id_content_user_map.values()))
    
    # 获取已有的归一化content集合
    # 如果有指定user，则获取该user的；否则获取整个client的
    user_for_existing = None
    for user, _ in user_configs:
        if user and user != 'all':
            user_for_existing = user
            break
    
    existing_dict = get_existing_norm_contents(None, client, user=user_for_existing, connector=connector, limit_num=limit_num)
    
    # 调用单级归一化
    norm_mapping = query_norm.norm_query_by_class(
        existing_query_dict=existing_dict,
        queries_to_classify=all_contents,
        embedding_config_path=embedding_config_path,
        similarity_threshold=similarity_threshold,
        query_info_dict=query_info_dict
    )
    
    logging.info(f"client={client} 单级归一化完成，共{len(norm_mapping)}个映射，归一到{len(set(norm_mapping.values()))}个content")
    return norm_mapping


def _update_norm_content_to_db(connector: MySQLConnector, client, id_content_user_map, norm_content_mapping, progress_step=1000):
    """
    将归一化结果更新到数据库（公用）
    """
    conn = connector.get_connection()
    update_cursor = conn.cursor()
    
    try:
        update_count = 0
        for id_, (content, user) in id_content_user_map.items():
            norm_content = norm_content_mapping.get(content, content)
            update_sql = "UPDATE data_chat_history SET norm_content=%s WHERE id=%s"
            try:
                update_cursor.execute(update_sql, (norm_content, id_))
                update_count += 1
                if update_count % progress_step == 0:
                    logging.info(f"client={client} 更新进度 {update_count}/{len(id_content_user_map)}")
            except Exception as e:
                logging.error(f"更新id={id_}失败: {e}")
        
        conn.commit()
        logging.info(f"client={client} 更新完成，成功更新{update_count}/{len(id_content_user_map)}条记录")
        
    finally:
        connector.close_connection(conn, update_cursor)


def batch_update_regular_content_from_sql(sql_config_path, start_time, end_time,
                                          need_cover=False, client_white_set=None,
                                          progress_step=1000, batch_date_range=10):
    """
    从rf_app_offline_task表获取regular_content任务配置，批量更新regular_content字段
    使用规则清洗方法（全小写+去除多余空白符）而非聚类归一化
    
    :param sql_config_path: 数据库配置文件路径
    :param start_time: 开始时间（%Y%m%d%H%M%S字符串、datetime或int）
    :param end_time: 结束时间（%Y%m%d%H%M%S字符串、datetime或int）
    :param need_cover: 是否覆盖已有结果，False则只更新regular_content为NULL或空的记录
    :param client_white_set: 白名单客户集合，为None则处理所有
    :param progress_step: 日志输出步长
    :param batch_date_range: 时间分片大小（天），每次处理这么多天的数据
    """
    _ensure_logging()
    
    if client_white_set:
        client_white_set = set(client_white_set.split(','))
    
    # 1. 从rf_app_offline_task获取regular_content任务配置
    connector_for_task = MySQLConnector(sql_config_path)
    conn = connector_for_task.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    config_dict = {}  # {(client, user): {item_key: item_value}}
    
    try:
        task_sql = """
            SELECT client, user, item_key, item_value 
            FROM rf_app_offline_task 
            WHERE task_type='regular_content'
        """
        cursor.execute(task_sql)
        rows = cursor.fetchall()
        
        for row in rows:
            client = row['client']
            user = row['user']
            # 处理user为None或空字符串的情况
            if user is None or str(user).strip() == '':
                user_key = None
            else:
                user_key = user.strip()
            if client_white_set and client not in client_white_set:
                continue
            item_key = row['item_key']
            item_value = row['item_value']
            key = (client, user_key)
            if key not in config_dict:
                config_dict[key] = {}
            config_dict[key][item_key] = item_value
    finally:
        connector_for_task.close_connection(conn, cursor)
    
    if not config_dict:
        logging.info("没有找到需要处理的regular_content任务配置")
        return
    
    # 过滤：只保留 enable=1 的任务配置
    enabled_config_dict = {}
    for key, item_map in config_dict.items():
        enable_value = item_map.get('enable')
        # 检查 enable 是否为 1（可能是字符串 '1' 或整数 1）
        if enable_value is not None and str(enable_value).strip() == '1':
            enabled_config_dict[key] = item_map
        else:
            client, user = key
            logging.info(f"跳过未启用的任务配置: client={client}, user={user}, enable={enable_value}")
    
    if not enabled_config_dict:
        logging.info("没有找到启用的regular_content任务配置（enable=1）")
        return
    
    # 使用过滤后的配置
    config_dict = enabled_config_dict
    logging.info(f"找到 {len(config_dict)} 个启用的regular_content任务配置")
    
    # 2. 时间格式化
    if isinstance(start_time, str):
        start_dt = datetime.strptime(start_time, '%Y%m%d%H%M%S')
    elif isinstance(start_time, datetime):
        start_dt = start_time
    elif isinstance(start_time, int):
        start_dt = datetime.strptime(str(start_time), '%Y%m%d%H%M%S')
    else:
        raise ValueError("start_time 必须是字符串(%Y%m%d%H%M%S)/int 或 datetime")

    if isinstance(end_time, str):
        end_dt = datetime.strptime(end_time, '%Y%m%d%H%M%S')
    elif isinstance(end_time, datetime):
        end_dt = end_time
    elif isinstance(end_time, int):
        end_dt = datetime.strptime(str(end_time), '%Y%m%d%H%M%S')
    else:
        raise ValueError("end_time 必须是字符串(%Y%m%d%H%M%S)/int 或 datetime")
    
    # 3. 按client分组
    clients_to_process = {}  # {client: [(user, config)]}
    for (client, user), item_map in config_dict.items():
        if client not in clients_to_process:
            clients_to_process[client] = []
        clients_to_process[client].append((user, item_map))
    
    # 4. 共享连接器
    shared_connector = MySQLConnector(sql_config_path)
    
    # 5. 处理每个client
    for client, user_configs in clients_to_process.items():
        # 获取user（regular_content不需要两级处理，直接取第一个user或all）
        fetch_user = user_configs[0][0]  # 取第一个user
        
        logging.info(f"开始处理client={client}, user={fetch_user}, 使用规则清洗方法")
        
        # 生成时间分片
        time_ranges = _generate_time_ranges(start_dt, end_dt, batch_date_range)
        total_batches = len(time_ranges)
        
        for batch_idx, (batch_start_str, batch_end_str) in enumerate(time_ranges, 1):
            try:
                logging.info(f"client={client} 开始批次 {batch_idx}/{total_batches}，区间 {batch_start_str} ~ {batch_end_str}")
                
                # ===== 第1步：获取数据 =====
                id_content_map = _fetch_regular_content_data(
                    connector=shared_connector,
                    client=client,
                    user=fetch_user,
                    start_time_formatted=batch_start_str,
                    end_time_formatted=batch_end_str,
                    need_cover=need_cover
                )
                logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 数据获取完成，共 {len(id_content_map)} 条")
                
                if not id_content_map:
                    logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 没有需要处理的数据")
                    continue
                
                # ===== 第2步：规则清洗 =====
                regular_content_mapping = {}  # {id: regular_content}
                for record_id, send_content in id_content_map.items():
                    regular_content_mapping[record_id] = query_norm.regular_content(send_content)
                
                logging.info(f"client={client} 批次 {batch_idx}/{total_batches} 规则清洗完成")
                
                # ===== 第3步：更新数据库 =====
                _update_regular_content_to_db(
                    connector=shared_connector,
                    regular_content_mapping=regular_content_mapping,
                    progress_step=progress_step
                )
                
            except Exception as e:
                logging.error(f"client={client} 批次 {batch_idx}/{total_batches} 处理失败，跳过。错误: {e}", exc_info=True)
                continue


def _fetch_regular_content_data(connector: MySQLConnector, client, user, start_time_formatted, end_time_formatted, need_cover):
    """
    从数据库获取需要进行规则清洗的content数据
    :return: {id: send_content} 字典
    """
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        select_sql = "SELECT id, send_content FROM data_chat_history WHERE customer=%s AND create_time >= %s AND create_time < %s"
        params = [client, start_time_formatted, end_time_formatted]
        if user and user != 'all':
            select_sql += " AND user=%s"
            params.append(user)
        if not need_cover:
            select_sql += " AND (regular_content IS NULL OR regular_content = '')"
        
        cursor.execute(select_sql, params)
        rows = cursor.fetchall()
        
        logging.info(f"client={client} 查询到{len(rows)}条数据")
        
        # 构建id到content的映射
        id_content_map = {}
        for row in rows:
            if row['send_content'] and row['send_content'].strip():
                id_content_map[row['id']] = row['send_content'].strip()
        
        logging.info(f"client={client} 有效数据{len(id_content_map)}条")
        return id_content_map
        
    finally:
        connector.close_connection(conn, cursor)


def _update_regular_content_to_db(connector: MySQLConnector, regular_content_mapping, progress_step):
    """
    将规则清洗结果批量更新到数据库
    :param regular_content_mapping: {id: regular_content}
    """
    conn = connector.get_connection()
    update_cursor = conn.cursor()
    
    try:
        total = len(regular_content_mapping)
        update_sql = "UPDATE data_chat_history SET regular_content=%s WHERE id=%s"
        
        logging.info(f"开始更新{total}条记录的regular_content字段")
        
        for idx, (record_id, regular_content) in enumerate(regular_content_mapping.items(), 1):
            update_cursor.execute(update_sql, (regular_content, record_id))
            
            if progress_step and idx % progress_step == 0:
                conn.commit()
                logging.info(f"更新进度 {idx}/{total}")
        
        conn.commit()
        logging.info(f"更新完成，共更新{total}条记录")
        
    finally:
        connector.close_connection(conn, update_cursor)


def _generate_time_ranges(start_dt: datetime, end_dt: datetime, batch_days: int):
    """
    将时间范围按天分段，返回[(start_str, end_str), ...]
    """
    ranges = []
    cur_start = start_dt
    delta = timedelta(days=batch_days)
    while cur_start < end_dt:
        cur_end = min(cur_start + delta, end_dt)
        ranges.append((
            cur_start.strftime('%Y-%m-%d %H:%M:%S'),
            cur_end.strftime('%Y-%m-%d %H:%M:%S')
        ))
        cur_start = cur_end
    return ranges


if __name__ == "__main__":
    # 示例参数
    import sys
    import fire
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
            '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s')
    fire.Fire()
