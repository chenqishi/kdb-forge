import logging
from kdb.shared.clients.mysql_connector import MySQLConnector
from datetime import datetime
import pandas as pd

def stat_column_distribution(sql_config, table_name, column_name, start_time=None, end_time=None, client_name=None, only_text=True):
    """
    统计指定表指定列的值分布，按占比从大到小排序。
    可选：开始时间、结束时间、client_name。
    data_chat_history表时client_name自动映射为customer。
    :param sql_config: 数据库配置文件路径
    :param table_name: 表名
    :param column_name: 列名
    :param start_time: 可选，开始时间（%Y%m%d%H%M%S 或 %Y-%m-%d %H:%M:%S）
    :param end_time: 可选，结束时间（%Y%m%d%H%M%S 或 %Y-%m-%d %H:%M:%S）
    :param client_name: 可选，客户名
    :param only_text: 是否只统计send_type为TEXT的（默认True）
    :return: list of (value, count, percent)
    """
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor()
    try:
        # 构造where条件
        wheres = []
        params = []
        # 字段名映射
        client_col = 'customer' if table_name == 'data_chat_history' else 'client'
        if client_name:
            wheres.append(f"{client_col}=%s")
            params.append(client_name)
        if start_time:
            # 自动识别格式
            if len(str(start_time)) == 14:
                start_time = datetime.strptime(str(start_time), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
            wheres.append("create_time >= %s")
            params.append(start_time)
        if end_time:
            if len(str(end_time)) == 14:
                end_time = datetime.strptime(str(end_time), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
            wheres.append("create_time < %s")
            params.append(end_time)
        if only_text and table_name == 'data_chat_history':
            wheres.append("send_type = 'TEXT'")
        where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ''
        # 统计总数
        total_sql = f"SELECT COUNT(*) FROM {table_name} {where_sql}"
        cursor.execute(total_sql, params)
        total = cursor.fetchone()[0]
        if total == 0:
            return []
        # 统计各值分布
        stat_sql = f"SELECT {column_name}, COUNT(*) as cnt FROM {table_name} {where_sql} GROUP BY {column_name} ORDER BY cnt DESC"
        cursor.execute(stat_sql, params)
        result = []
        other_count = 0
        for value, cnt in cursor.fetchall():
            if value is None or (isinstance(value, str) and (value.strip() == '' or value.strip() in ['其他', '其它'])):
                other_count += cnt
            else:
                percent = cnt / total
                result.append((value, cnt, percent))
        if other_count > 0:
            percent = other_count / total
            result.append(('其它', other_count, percent))
        return result
    finally:
        cursor.close()
        conn.close()


def gen_top_num_report_excel(sql_config, save_excel_file, start_time=None, end_time=None, client_name=None):
    """
    产出一个excel，包含：
    1. 详情表（对象、消息内容、消息类别，筛选send_type=TEXT）
    2. top问题表分布（send_content分布，列名：问题,占比）
    3. 问题类别分布（content_category分布，列名：类别,占比）
    """
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    # 1. 详情表
    wheres = ["send_type = 'TEXT'"]
    params = []
    if client_name:
        wheres.append("customer=%s")
        params.append(client_name)
    if start_time:
        if len(str(start_time)) == 14:
            start_time = datetime.strptime(str(start_time), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        wheres.append("create_time >= %s")
        params.append(start_time)
    if end_time:
        if len(str(end_time)) == 14:
            end_time = datetime.strptime(str(end_time), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        wheres.append("create_time < %s")
        params.append(end_time)
    where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    #detail_sql = f"SELECT other_user_nickname, send_content, content_category FROM data_chat_history {where_sql}"
    detail_sql = f"SELECT * FROM data_chat_history {where_sql}"
    df_detail = pd.read_sql(detail_sql, conn, params=params)
    #df_detail.columns = ['对象', '消息内容', '消息类别']
    # 2. top问题表分布
    top_q = stat_column_distribution(sql_config, 'data_chat_history', 'send_content', start_time, end_time, client_name, only_text=True)
    df_top_q = pd.DataFrame(top_q, columns=['问题', '计数', '占比'])
    df_top_q = df_top_q[['问题', '占比']]
    if not df_top_q.empty:
        df_top_q['占比'] = (df_top_q['占比'] * 100).round(2).astype(str) + '%'
    # 3. 问题类别分布
    cate_dist = stat_column_distribution(sql_config, 'data_chat_history', 'content_category', start_time, end_time, client_name, only_text=True)
    df_cate = pd.DataFrame(cate_dist, columns=['类别', '计数', '占比'])
    df_cate = df_cate[['类别', '占比']]
    if not df_cate.empty:
        df_cate['占比'] = (df_cate['占比'] * 100).round(2).astype(str) + '%'
    # 写入excel
    with pd.ExcelWriter(save_excel_file, engine='openpyxl') as writer:
        df_detail.to_excel(writer, sheet_name='详情表', index=False)
        df_top_q.to_excel(writer, sheet_name='top问题表分布', index=False)
        df_cate.to_excel(writer, sheet_name='问题类别分布', index=False)
    conn.close()


if __name__ == '__main__':
    import sys
    import fire
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
            '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s')
    fire.Fire()
