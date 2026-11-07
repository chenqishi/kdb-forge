import json
import logging
import time
from kdb.shared.clients.mysql_connector import MySQLConnector


def sql_database_transfer(from_sql_config, to_sql_config, table_config_file, is_all_table=0, trans_data_count_limit=1000):
    """
    将from_sql_config中配置的mysql数据迁移到to_sql_config配置的数据库
    
    Args:
        from_sql_config: 源数据库配置文件路径
        to_sql_config: 目标数据库配置文件路径  
        table_config_file: 表配置文件名，格式为table_name\tis_need_trans_data
        is_all_table: 是否迁移所有表 (0=否, 1=是)
        trans_data_count_limit: 数据迁移行数限制
    """
    
    # 1) 载入table_config_file为字典
    table_config = load_table_config(table_config_file)
    logging.info(f"加载表配置: {len(table_config)} 个表")
    
    # 初始化数据库连接
    from_connector = MySQLConnector(from_sql_config)
    to_connector = MySQLConnector(to_sql_config)
    
    from_conn = from_connector.get_connection()
    to_conn = to_connector.get_connection()
    
    if not from_conn or not to_conn:
        logging.error("无法建立数据库连接")
        return
    
    from_cursor = from_conn.cursor()
    to_cursor = to_conn.cursor()
    
    try:
        # 2) 获取from_sql_config的所有表
        all_tables = get_all_tables(from_cursor)
        logging.info(f"源数据库共有 {len(all_tables)} 个表")
        
        # 统计信息
        stats = {
            'total_tables': len(all_tables),
            'config_tables': len(table_config),
            'schema_only': 0,
            'schema_and_data': 0,
            'skipped': 0,
            'errors': 0
        }
        
        # 3) 处理每个表
        for table_name in all_tables:
            try:
                result = process_table(
                    table_name, table_config, is_all_table, 
                    trans_data_count_limit, from_cursor, to_cursor
                )
                stats[result] += 1
                logging.info(f"表 {table_name}: {result}")
                
            except Exception as e:
                logging.error(f"处理表 {table_name} 时出错: {e}")
                stats['errors'] += 1
        
        # 输出迁移情况
        print_migration_summary(stats)
        
    finally:
        from_cursor.close()
        to_cursor.close()
        from_connector.close_connection(from_conn, from_cursor)
        to_connector.close_connection(to_conn, to_cursor)


def load_table_config(table_config_file):
    """
    加载表配置文件为字典
    格式: table_name\tis_need_trans_data
    """
    table_config = {}
    
    if not table_config_file:
        return table_config
        
    try:
        with open(table_config_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                parts = line.split('\t')
                if len(parts) != 2:
                    logging.warning(f"表配置文件第{line_num}行格式错误: {line}")
                    continue
                    
                table_name = parts[0].strip()
                is_need_trans_data = parts[1].strip()
                
                if is_need_trans_data not in ['0', '1']:
                    logging.warning(f"表配置文件第{line_num}行数据迁移标识错误: {is_need_trans_data}")
                    continue
                    
                table_config[table_name] = int(is_need_trans_data)
                
    except FileNotFoundError:
        logging.warning(f"表配置文件不存在: {table_config_file}")
    except Exception as e:
        logging.error(f"读取表配置文件失败: {e}")
        
    return table_config


def get_all_tables(cursor):
    """
    获取数据库中的所有表名
    """
    cursor.execute("SHOW TABLES")
    tables = [row[0] for row in cursor.fetchall()]
    return tables


def get_table_row_count(cursor, table_name):
    """
    获取表的行数
    """
    cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
    return cursor.fetchone()[0]


def get_table_create_sql(cursor, table_name):
    """
    获取表的CREATE SQL语句
    """
    cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
    return cursor.fetchone()[1]


def process_table(table_name, table_config, is_all_table, trans_data_count_limit, from_cursor, to_cursor):
    """
    处理单个表的迁移
    """
    
    # a. 在table_config_file中的表，按照table_config_file配置的操作
    if table_name in table_config:
        is_need_trans_data = table_config[table_name]
        
        # 先迁移表结构
        migrate_table_schema(table_name, from_cursor, to_cursor)
        
        if is_need_trans_data == 1:
            # 迁移数据
            migrate_table_data(table_name, from_cursor, to_cursor)
            return 'schema_and_data'
        else:
            return 'schema_only'
    
    # b. 不在的，若is_all_table=1，且数据量<trans_data_count_limit，则进行数据迁移
    # c. 不在的，若is_all_table=1，且数据量>=trans_data_count_limit，则只进行表定义迁移
    elif is_all_table == 1:
        row_count = get_table_row_count(from_cursor, table_name)
        
        # 先迁移表结构
        migrate_table_schema(table_name, from_cursor, to_cursor)
        
        if row_count < trans_data_count_limit:
            # 迁移数据
            migrate_table_data(table_name, from_cursor, to_cursor)
            return 'schema_and_data'
        else:
            logging.info(f"表 {table_name} 数据量 {row_count} 超过限制 {trans_data_count_limit}，只迁移表结构")
            return 'schema_only'
    
    else:
        return 'skipped'


def migrate_table_schema(table_name, from_cursor, to_cursor):
    """
    迁移表结构
    """
    try:
        # 获取源表的CREATE语句
        create_sql = get_table_create_sql(from_cursor, table_name)
        
        # 在目标数据库中创建表（如果不存在）
        # 先删除可能存在的表
        to_cursor.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        
        # 创建表
        to_cursor.execute(create_sql)
        
        logging.info(f"成功迁移表结构: {table_name}")
        
    except Exception as e:
        logging.error(f"迁移表结构失败 {table_name}: {e}")
        raise


def migrate_table_data(table_name, from_cursor, to_cursor):
    """
    迁移表数据（不清空目标表旧数据）
    """
    try:
        # 获取表的列信息
        from_cursor.execute(f"DESCRIBE `{table_name}`")
        columns = [row[0] for row in from_cursor.fetchall()]
        
        # 获取数据
        from_cursor.execute(f"SELECT * FROM `{table_name}`")
        rows = from_cursor.fetchall()
        
        if not rows:
            logging.info(f"表 {table_name} 没有数据需要迁移")
            return
            
        # 插入数据（不清空目标表，直接追加）
        placeholders = ', '.join(['%s'] * len(columns))
        insert_sql = f"INSERT INTO `{table_name}` VALUES ({placeholders})"
        
        # 分批插入数据
        batch_size = 1000
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            to_cursor.executemany(insert_sql, batch)
        
        logging.info(f"成功迁移表数据: {table_name}, 共 {len(rows)} 行（追加到目标表）")
        
    except Exception as e:
        logging.error(f"迁移表数据失败 {table_name}: {e}")
        raise


def print_migration_summary(stats):
    """
    输出迁移情况摘要
    """
    print("\n" + "="*50)
    print("数据库迁移完成摘要")
    print("="*50)
    print(f"总表数: {stats['total_tables']}")
    print(f"配置表数: {stats['config_tables']}")
    print(f"只迁移表结构: {stats['schema_only']}")
    print(f"迁移表结构和数据: {stats['schema_and_data']}")
    print(f"跳过表: {stats['skipped']}")
    print(f"错误表: {stats['errors']}")
    print("="*50)

def transfer_es_data(source_config_path, target_config_path, source_index_name, target_index_name, batch_size=100):
    """
    将source_config中配置的ES数据迁移到target_config配置的ES
    迁移数据时不包含embedding字段，会通过insert_data接口重新计算embedding
    
    Args:
        source_config_path: 源配置文件路径（search_index配置格式）
        target_config_path: 目标配置文件路径（search_index配置格式）
        source_index_name: 源索引名称
        target_index_name: 目标索引名称（可与源索引名不同，实现同集群内索引迁移）
        batch_size: 批量处理大小
    """
    import sys
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
    from kdb.retrieval.engines.es_search_interface import EsSearchInterface
    
    logging.info(f"开始迁移ES数据: 源索引={source_index_name}, 目标索引={target_index_name}")
    
    # 1. 加载源和目标配置
    try:
        source_config = json.load(open(source_config_path, 'r', encoding='utf-8'))
        target_config = json.load(open(target_config_path, 'r', encoding='utf-8'))
        logging.info(f"成功加载配置文件")
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        return
    
    # 2. 初始化源ES接口（用于读取数据）
    try:
        source_es_engine_config = source_config.get('search_engine_config_path')
        source_es_interface = EsSearchInterface(config_path=source_es_engine_config, index_name=source_index_name)
        logging.info(f"成功初始化源ES接口")
    except Exception as e:
        logging.error(f"初始化源ES接口失败: {e}")
        return
    
    # 3. 初始化目标SearchDataInterface（用于写入数据，会自动计算embedding）
    try:
        target_search_interface = SearchDataInterface(config_path=target_config_path, index_name=target_index_name)
        logging.info(f"成功初始化目标SearchDataInterface")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logging.error(f"初始化目标SearchDataInterface失败: {e}\n{tb}")
        return
    
    # 3.5. 初始化目标ES查询接口（用于检查文档是否已存在）
    try:
        target_es_engine_config = target_config.get('search_engine_config_path')
        target_es_interface = EsSearchInterface(config_path=target_es_engine_config, index_name=target_index_name)
        logging.info(f"成功初始化目标ES查询接口")
    except Exception as e:
        logging.error(f"初始化目标ES查询接口失败: {e}")
        return
    
    # 4. 使用scroll API获取所有文档
    try:
        # 构造查询所有数据的query
        query = {}  # 空查询表示获取所有数据
        
        stats = {
            'total_processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        logging.info(f"开始从源ES读取数据...")
        
        # 使用scroll_search遍历所有文档
        for doc in source_es_interface.scroll_search(query, batch_size=batch_size, scroll_timeout='10m', index_names=source_index_name):
            stats['total_processed'] += 1
            
            try:
                # 5. 过滤掉包含"embedding"的字段
                filtered_doc = filter_embedding_fields(doc)
                
                # 5.5. 检查目标ES中是否已存在该文档ID
                doc_id = filtered_doc.get('_id')
                if doc_id:
                    try:
                        # 使用get方法检查文档是否存在，如果不存在返回None
                        existing_doc = target_es_interface.get(
                            data_id=doc_id,
                            index_names=target_index_name
                        )
                        
                        # 如果文档存在（get返回非None），跳过该文档
                        if existing_doc is not None:
                            stats['skipped'] += 1
                            if stats['total_processed'] % 100 == 0:
                                logging.info(f"已处理 {stats['total_processed']} 条数据，成功 {stats['success']} 条，跳过 {stats['skipped']} 条")
                            continue
                    except Exception as check_error:
                        # 如果检查失败，记录日志但继续尝试插入
                        logging.warning(f"检查文档是否存在时出错 (ID: {doc_id}): {check_error}")
                
                # 6. 使用insert_data重新插入，会自动计算embedding
                # check_duplicate设为False，因为是迁移数据，不需要查重
                success, message = target_search_interface.insert_data(
                    filtered_doc, 
                    check_duplicate=False,
                    index_name=target_index_name,
                    refresh_imm=False  # 不立即刷新，提高性能
                )
                
                if success:
                    stats['success'] += 1
                    if stats['total_processed'] % 100 == 0:
                        logging.info(f"已处理 {stats['total_processed']} 条数据，成功 {stats['success']} 条，跳过 {stats['skipped']} 条")
                else:
                    stats['failed'] += 1
                    logging.warning(f"插入数据失败: {filtered_doc.get('_id')}, 原因: {message}")
                    
            except Exception as e:
                stats['failed'] += 1
                logging.error(f"处理文档失败: {doc.get('_id')}, 错误: {e}")
                continue
        
        # 7. 输出迁移统计信息
        print_es_migration_summary(stats, f"{source_index_name} -> {target_index_name}")
        
    except Exception as e:
        logging.error(f"迁移过程中出错: {e}")
        import traceback
        logging.error(traceback.format_exc())


def filter_embedding_fields(doc: dict) -> dict:
    """
    过滤掉文档中包含"embedding"的字段
    
    Args:
        doc: 原始文档
    Returns:
        过滤后的文档
    """
    filtered_doc = {}
    
    for key, value in doc.items():
        # 跳过字段名包含"embedding"的字段
        if 'embedding' in key.lower():
            continue
        
        # 如果是字典，递归过滤
        if isinstance(value, dict):
            filtered_value = filter_embedding_fields(value)
            if filtered_value:  # 只保留非空字典
                filtered_doc[key] = filtered_value
        # 如果是列表，遍历过滤
        elif isinstance(value, list):
            filtered_list = []
            for item in value:
                if isinstance(item, dict):
                    filtered_item = filter_embedding_fields(item)
                    if filtered_item:
                        filtered_list.append(filtered_item)
                else:
                    filtered_list.append(item)
            if filtered_list:  # 只保留非空列表
                filtered_doc[key] = filtered_list
        else:
            filtered_doc[key] = value
    
    return filtered_doc


def print_es_migration_summary(stats: dict, index_name: str):
    """
    输出ES迁移情况摘要
    """
    print("\n" + "="*60)
    print(f"ES数据迁移完成摘要 - 索引: {index_name}")
    print("="*60)
    print(f"总处理数: {stats['total_processed']}")
    print(f"成功数: {stats['success']}")
    print(f"失败数: {stats['failed']}")
    print(f"跳过数: {stats['skipped']}")
    print(f"成功率: {stats['success']/stats['total_processed']*100:.2f}%" if stats['total_processed'] > 0 else "N/A")
    print("="*60)


def get_all_indices(es_config_path):
    """
    获取ES中的所有索引名称
    
    Args:
        es_config_path: ES引擎配置文件路径
    Returns:
        List[str]: 索引名称列表
    """
    from kdb.retrieval.engines.es_search_interface import EsSearchInterface
    
    try:
        # 创建临时的ES接口（不指定index_name）
        config = json.load(open(es_config_path, 'r', encoding='utf-8'))
        es_engine_config = config.get('search_engine_config_path')
        temp_es_config = json.load(open(es_engine_config, 'r', encoding='utf-8'))
        temp_es_config['index_name'] = '_all'  # 临时索引名
        
        # 创建ES接口
        es_interface = EsSearchInterface(
            hosts=temp_es_config.get('hosts'),
            index_name=temp_es_config.get('index_name'),
            username=temp_es_config.get('username'),
            password=temp_es_config.get('password'),
            vector_fields=temp_es_config.get('vector_fields')
        )
        
        # 获取所有索引
        # 使用 cat.indices API 获取索引列表
        indices_info = es_interface.es.cat.indices(format='json')
        
        # 过滤掉系统索引（以.开头的）
        index_names = [
            index['index'] 
            for index in indices_info 
            if not index['index'].startswith('.')
        ]
        
        logging.info(f"获取到 {len(index_names)} 个索引: {index_names}")
        return index_names
        
    except Exception as e:
        logging.error(f"获取索引列表失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return []


def batch_transfer_es_data(source_config_path, target_config_path, index_name, black_index, batch_size=100):
    """
    批量迁移ES数据，支持多个索引
    
    Args:
        source_config_path: 源配置文件路径（search_index配置格式）
        target_config_path: 目标配置文件路径（search_index配置格式）
        index_name: 索引名称，支持：
                    - 单个索引名: "index1"
                    - 多个索引名（逗号分隔）: "index1,index2,index3"
                    - 所有索引: "all"
        black_index: 黑名单索引列表
        batch_size: 批量处理大小
    """
    logging.info(f"开始批量迁移ES数据")
    
    # 1. 解析index_name参数
    if index_name.lower() == 'all':
        # 获取所有索引
        logging.info("获取所有索引...")
        index_list = get_all_indices(source_config_path)
        if not index_list:
            logging.error("未能获取到任何索引")
            return
    else:
        # 解析逗号分隔的索引名
        index_list = [name.strip() for name in index_name.split(',') if name.strip()]
    
    if not index_list:
        logging.error("索引列表为空")
        return
    
    logging.info(f"准备迁移 {len(index_list)} 个索引: {index_list}")
    if isinstance(black_index, str):
        black_index = black_index.split(",")
    elif isinstance(black_index, tuple):
        black_index = list(black_index)
    black_index_set = set(black_index)

    
    # 2. 统计信息
    batch_stats = {
        'total_indices': len(index_list),
        'success_indices': 0,
        'failed_indices': 0,
        'total_documents': 0,
        'success_documents': 0,
        'failed_documents': 0,
        'index_details': []
    }
    
    # 3. 逐个迁移索引
    for i, idx_name in enumerate(index_list, 1):
        if idx_name in black_index_set:
            logging.info(f"索引 {idx_name} 在黑名单中，跳过迁移")
            continue
        logging.info(f"\n{'='*70}")
        logging.info(f"开始迁移索引 [{i}/{len(index_list)}]: {idx_name}")
        logging.info(f"{'='*70}")
        
        try:
            # 调用单索引迁移函数
            index_start_time = time.time()
            
            # 调用时，source_index_name和target_index_name都填相同的值
            stats = _transfer_single_index(
                source_config_path=source_config_path,
                target_config_path=target_config_path,
                source_index_name=idx_name,
                target_index_name=idx_name,
                batch_size=batch_size
            )
            
            index_end_time = time.time()
            index_duration = index_end_time - index_start_time
            
            # 更新统计信息
            if stats['total_processed'] > 0 and stats['failed'] < stats['total_processed']:
                batch_stats['success_indices'] += 1
            else:
                batch_stats['failed_indices'] += 1
            
            batch_stats['total_documents'] += stats['total_processed']
            batch_stats['success_documents'] += stats['success']
            batch_stats['failed_documents'] += stats['failed']
            
            # 记录详细信息
            batch_stats['index_details'].append({
                'index_name': idx_name,
                'total': stats['total_processed'],
                'success': stats['success'],
                'failed': stats['failed'],
                'duration': index_duration
            })
            
            logging.info(f"索引 {idx_name} 迁移完成，耗时: {index_duration:.2f}秒")
            
        except Exception as e:
            batch_stats['failed_indices'] += 1
            batch_stats['index_details'].append({
                'index_name': idx_name,
                'total': 0,
                'success': 0,
                'failed': 0,
                'error': str(e)
            })
            logging.error(f"迁移索引 {idx_name} 失败: {e}")
            import traceback
            logging.error(traceback.format_exc())
            continue
    
    # 4. 输出总体统计信息
    print_batch_migration_summary(batch_stats)


def _transfer_single_index(source_config_path, target_config_path, source_index_name, target_index_name, batch_size):
    """
    迁移单个索引（内部函数，返回统计信息）
    
    Args:
        source_config_path: 源配置文件路径
        target_config_path: 目标配置文件路径
        source_index_name: 源索引名称
        target_index_name: 目标索引名称
        batch_size: 批量处理大小
    Returns:
        dict: 统计信息
    """
    import sys
    from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
    from kdb.retrieval.engines.es_search_interface import EsSearchInterface
    
    # 1. 加载源和目标配置
    source_config = json.load(open(source_config_path, 'r', encoding='utf-8'))
    target_config = json.load(open(target_config_path, 'r', encoding='utf-8'))
    
    # 2. 初始化源ES接口（用于读取数据）
    source_es_engine_config = source_config.get('search_engine_config_path')
    source_es_interface = EsSearchInterface(config_path=source_es_engine_config, index_name=source_index_name)
    
    # 3. 初始化目标SearchDataInterface（用于写入数据，会自动计算embedding）
    target_search_interface = SearchDataInterface(config_path=target_config_path, index_name=target_index_name)
    
    # 4. 使用scroll API获取所有文档
    query = {}  # 空查询表示获取所有数据
    
    stats = {
        'total_processed': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0
    }
    
    # 使用scroll_search遍历所有文档
    for doc in source_es_interface.scroll_search(query, batch_size=batch_size, scroll_timeout='10m', index_names=source_index_name):
        stats['total_processed'] += 1
        
        try:
            # 过滤掉包含"embedding"的字段
            filtered_doc = filter_embedding_fields(doc)
            
            # 使用insert_data重新插入，会自动计算embedding
            success, message = target_search_interface.insert_data(
                filtered_doc, 
                check_duplicate=False,
                index_name=target_index_name,
                refresh_imm=False
            )
            
            if success:
                stats['success'] += 1
                if stats['total_processed'] % 100 == 0:
                    logging.info(f"已处理 {stats['total_processed']} 条数据，成功 {stats['success']} 条")
            else:
                stats['failed'] += 1
                logging.warning(f"插入数据失败: {filtered_doc.get('_id')}, 原因: {message}")
                
        except Exception as e:
            stats['failed'] += 1
            logging.error(f"处理文档失败: {doc.get('_id')}, 错误: {e}")
            continue
    
    return stats


def print_batch_migration_summary(batch_stats):
    """
    输出批量迁移统计摘要
    """
    print("\n" + "="*70)
    print("批量ES数据迁移完成摘要")
    print("="*70)
    print(f"\n索引统计:")
    print(f"  总索引数: {batch_stats['total_indices']}")
    print(f"  成功索引数: {batch_stats['success_indices']}")
    print(f"  失败索引数: {batch_stats['failed_indices']}")
    print(f"  索引成功率: {batch_stats['success_indices']/batch_stats['total_indices']*100:.2f}%" if batch_stats['total_indices'] > 0 else "N/A")
    
    print(f"\n文档统计:")
    print(f"  总文档数: {batch_stats['total_documents']}")
    print(f"  成功文档数: {batch_stats['success_documents']}")
    print(f"  失败文档数: {batch_stats['failed_documents']}")
    print(f"  文档成功率: {batch_stats['success_documents']/batch_stats['total_documents']*100:.2f}%" if batch_stats['total_documents'] > 0 else "N/A")
    
    print(f"\n各索引详情:")
    print(f"{'索引名称':<30} {'文档数':<10} {'成功':<10} {'失败':<10} {'耗时(秒)':<10}")
    print("-"*70)
    for detail in batch_stats['index_details']:
        if 'error' in detail:
            print(f"{detail['index_name']:<30} {'ERROR':<10} {'-':<10} {'-':<10} {'-':<10}")
            print(f"  错误: {detail['error']}")
        else:
            duration = detail.get('duration', 0)
            print(f"{detail['index_name']:<30} {detail['total']:<10} {detail['success']:<10} {detail['failed']:<10} {duration:<10.2f}")
    
    print("="*70)

    
if __name__ == "__main__":
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.INFO, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    fire.Fire()
    