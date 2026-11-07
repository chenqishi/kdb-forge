from collections import namedtuple, OrderedDict
from commons.mysql_connector import MySQLConnector

class ChatContextControl(object):
    """
    聊天上下文缓存控制，支持LRU缓存
    """
    def __init__(self, config_path, catche_num):
        self.config_path = config_path
        self.catche_num = catche_num
        self.cache = OrderedDict()  # session_id -> [namedtuple, ...]

        # 动态获取字段名
        connector = MySQLConnector(config_path)
        conn = connector.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SHOW COLUMNS FROM data_online_sessions")
            self.fields = [row['Field'] for row in cursor.fetchall()]
            self.SessionData = namedtuple('SessionData', self.fields)
        finally:
            connector.close_connection(conn, cursor)

    def get_session_context(self, session_id):
        # 先查缓存
        if session_id in self.cache:
            # LRU: 访问后移到末尾
            self.cache.move_to_end(session_id)
            # 按create_time升序排序
            return sorted(self.cache[session_id], key=lambda x: getattr(x, 'create_time', None))

        # 缓存没有，查数据库
        connector = MySQLConnector(self.config_path)
        conn = connector.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            sql = "SELECT * FROM data_online_sessions WHERE session_id = %s ORDER BY create_time ASC"
            cursor.execute(sql, (session_id,))
            result = []
            for row in cursor:
                row_data = [row.get(f, None) for f in self.fields]
                result.append(self.SessionData(*row_data))
        finally:
            connector.close_connection(conn, cursor)

        # 写入缓存
        if len(self.cache) >= self.catche_num:
            # 淘汰最久未访问
            self.cache.popitem(last=False)
        # 按create_time升序排序
        result_sorted = sorted(result, key=lambda x: getattr(x, 'create_time', None))
        self.cache[session_id] = result_sorted
        return result_sorted

def get_chat_history_from_sql_iterator(config_path, customer, user=None, session_id=None, limit_num=None):
    """
    动态获取字段名，从data_chat_history表中筛选数据，返回namedtuple迭代器
    :param config_path: 数据库配置文件路径
    :param customer: 客户名
    :param session_id: 会话ID（可选）
    :return: 迭代器，每个元素为namedtuple
    """
    # 连接数据库
    connector = MySQLConnector(config_path)
    conn = connector.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 动态获取字段名
        cursor.execute("SHOW COLUMNS FROM data_chat_history")
        fields = [row['Field'] for row in cursor.fetchall()]
        ChatHistory = namedtuple('ChatHistory', fields)

        # 构造SQL
        sql = "SELECT * FROM data_chat_history WHERE customer = %s"
        params = [customer]
        if user is not None:
            sql += " AND user = %s"
            params.append(user)
        if session_id is not None:
            sql += " AND session_id = %s"
            params.append(session_id)
        sql += " ORDER BY create_time DESC"
        if limit_num is not None:
            sql += " LIMIT %s"
            params.append(limit_num)
        cursor.execute(sql, params)
        result = []
        for row in cursor:
            row_data = [row.get(f, None) for f in fields]
            result.append(ChatHistory(*row_data))
        # 反转，按时间正序返回
        for item in reversed(result):
            yield item
    finally:
        connector.close_connection(conn, cursor)
