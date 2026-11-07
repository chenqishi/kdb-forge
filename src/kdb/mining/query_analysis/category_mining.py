from kdb.shared.config.private_values import private_value as _private_value
import sys
import logging

from datetime import datetime
from collections import defaultdict

from kdb.shared.clients.mysql_connector import MySQLConnector
from kdb.shared.clients import dify_tools
from kdb.mining.query_analysis import category_manage
import random
from kdb.shared.config.legacy_config import GLOBAL_CONFIG
def gen_category_from_chat_history(sql_config, client_name, start_time, end_time):
    """
    从chat_history表中读取指定客户、时间范围内的send_content，生成类目。
    :param sql_config: 数据库配置文件路径
    :param client_name: 客户名
    :param start_time: 开始时间
    :param end_time: 结束时间
    """

    # 适配时间格式
    def parse_time(t):
        if isinstance(t, datetime):
            return t.strftime('%Y-%m-%d %H:%M:%S')
        t = str(t)
        if len(t) == 14 and t.isdigit():
            return datetime.strptime(t, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
        return t
    start_time_fmt = parse_time(start_time)
    end_time_fmt = parse_time(end_time)
    # 1. 获取聊天内容
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 获取聊天内容
        cursor.execute(
            """
            SELECT other_user_nickname, from_user_nickname, send_content, create_time
            FROM data_chat_history
            WHERE customer=%s AND create_time >= %s AND create_time < %s AND send_content IS NOT NULL AND send_content != ''
            ORDER BY other_user_nickname, create_time
            """,
            (client_name, start_time_fmt, end_time_fmt)
        )
        rows = cursor.fetchall()
        # 按other_user_nickname分组
        chat_dict = defaultdict(list)
        history_num = 0
        for row in rows:
            other_user_nickname = row['other_user_nickname'] or '未知用户'
            send_name = row['from_user_nickname'] or '未知发送者'
            send_content = row['send_content']
            chat_dict[other_user_nickname].append(f"{send_name}:{send_content}")
            history_num += 1

        logging.info(f"自动挖掘类目，获取{client_name} {start_time_fmt} {end_time_fmt} 聊天记录{history_num}条, 群数={len(chat_dict)}")
        # 拼接chat_history_str

        # 2. 获取已有类目
        cursor.execute(
            """
            SELECT cate1, cate2 FROM data_content_category WHERE client=%s OR client='global_use'
            """,
            (client_name,)
        )
        categories = cursor.fetchall()
        category_set = set(f"{row['cate1']}-{row['cate2']}" for row in categories if row['cate1'] and row['cate2'])
        # 3. 获取dify workflow配置
        cursor.execute(
            """
            SELECT item_key, item_value FROM rf_app_offline_task WHERE client=%s AND task_type='category_mining'
            """,
            (client_name,)
        )
        task_conf = {row['item_key']: row['item_value'] for row in cursor.fetchall()}
        dify_base_url = task_conf.get('dify_base_url', GLOBAL_CONFIG['dify_api_base'])
        dify_api_key = task_conf.get('dify_api_key', _private_value('4c755de112292e5788b06984'))
        system_prompt = task_conf.get('system_prompt', None)
    finally:
        connector.close_connection(conn, cursor)
    # 4. 请求dify workflow，直接用dify_tools.DifyWorkFlowRequest
    from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
    dify = DifyWorkFlowRequest(api_base=dify_base_url, api_key=dify_api_key, system_prompt=system_prompt)
    result = []
    all_category_set = category_set.copy()
    for user, contents in chat_dict.items():
        if len(contents) > 4000:
            contents = contents[:4000]
        category_str = "\n".join(all_category_set)
        chat_history_str = f"发生在群或单聊场景{user}的对话记录如下:\n" + "\n".join(contents) 
        one_result = dify.request_dify(chat_history_str, other_inputs={'category_set': category_str})
        result.append(one_result)
        all_category_set.update([l.strip() for l in one_result.split('\n') if l.strip()])
    # 5. 解析返回，去重输出
    result_str = "\n".join(result)
    final_category_set = set()
    if result_str:
        lines = [line.strip() for line in result_str.split('\n') if line.strip()]
        unique_lines = sorted(set(lines)) 
        for cate in unique_lines:
            if cate not in category_set:
                print(cate)
                final_category_set.add(cate)
    else:
        print('未获取到分类结果')
    return final_category_set


def category_auto_mining_and_update(sql_config, client_name, start_time, end_time):
    """
    自动挖掘类目并更新到数据库
    """
    # 1. 获取配置
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT item_key, item_value FROM rf_app_offline_task WHERE client=%s AND task_type='category_mining'
            """,
            (client_name,)
        )
        task_conf = {row['item_key']: row['item_value'] for row in cursor.fetchall()}
        auto_mining_num_limit = int(task_conf.get('auto_mining_num_limit', 0))
        # 2. 查询已有类目数量
        cursor.execute(
            """
            SELECT COUNT(*) as cnt FROM data_content_category WHERE client=%s 
            """,
            (client_name,)
        )
        cate_count = cursor.fetchone()['cnt']
    finally:
        connector.close_connection(conn, cursor)
    # 3. 判断是否需要自动挖掘
    if cate_count < auto_mining_num_limit:
        # 自动挖掘
        new_cate_set = gen_category_from_chat_history(sql_config, client_name, start_time, end_time)
        if len(new_cate_set) > auto_mining_num_limit:
            new_cate_set = random.sample(new_cate_set, auto_mining_num_limit)
        if new_cate_set:
            # 写入数据库
            category_manage.update_category(sql_config, client_name, list(new_cate_set))
            print(f"已自动挖掘并写入{len(new_cate_set)}个新类目")
        else:
            print("未挖掘到新类目")
        return len(new_cate_set)
    else:
        print(f"{client_name}已有类目数量{cate_count}，不低于自动挖掘阈值{auto_mining_num_limit}，无需自动挖掘")
        return 0

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()

    