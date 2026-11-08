import hashlib
from datetime import datetime as dt
from kdb.shared.database.mysql import MySQLConnector
import logging
import sys

def md5_id(text):
    if not text:
        return None
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def update_category(sql_config, client_name, category_file):
    """
    读取category_file（每行格式为cate1-cate2或cate1），写入data_content_category表。
    cate1id为cate1的md5，cate2id为{cate1}-{cate2}的md5，缺失都为空。
    :param sql_config: 数据库配置文件路径
    :param client_name: 客户名
    :param category_file: 类目文件路径
    """
    connector = MySQLConnector(sql_config)
    conn = connector.get_connection()
    cursor = conn.cursor()
    now = dt.now().strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(category_file, str):
        category_set = set()
        with open(category_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                category_set.add(line)
    else:
        category_set = category_file

    for cate in category_set:
        if '-' in cate:
            cate1, cate2 = cate.split('-', 1)
            cate1 = cate1.strip()
            cate2 = cate2.strip()
        else:
            cate1 = cate.strip()
            cate2 = ''
        cate1_id = md5_id(cate1) if cate1 else None
        cate2_id = md5_id(f"{cate1}-{cate2}") if cate1 and cate2 else None
        sql = """
            INSERT INTO data_content_category (client, customer, cate1, global_cate1_id, cate2, global_cate2_id, create_time, update_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        try:
            cursor.execute(sql, (client_name, client_name, cate1 or None, cate1_id, cate2 or None, cate2_id, now, now))
        except Exception as e:
            print(f"写入失败: {cate}, 错误: {e}")
    conn.commit()
    cursor.close()
    conn.close()





if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
