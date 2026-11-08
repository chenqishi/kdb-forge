from kdb.shared.database.mysql import MySQLConnector
import logging

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
