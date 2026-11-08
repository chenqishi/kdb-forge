import os
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.database.mysql import MySQLConnector
import traceback
import logging

class QueryCategoryDify:
    def __init__(self, config_path, client, dify_api_base, dify_api_key, system_prompt=None):
        """
        初始化，包括：
        1. 初始化dify模型
        2. 初始化类目字典，从sql data_content_category表中获取指定client的类目集合
        :param config_path: 数据库配置文件路径
        :param client: 客户名
        :param dify_api_base: dify模型API base url
        :param dify_api_key: dify模型API key
        :param system_prompt: 可选，dify系统提示词
        """
        self.client = client
        self.category_set = self._load_category_set(config_path, client)
        if system_prompt:
            category_str = '\n'.join(self.category_set)
            system_prompt = system_prompt.format(category_set=category_str)
        self.dify_model = DifyWorkFlowRequest(api_base=dify_api_base, api_key=dify_api_key, system_prompt=system_prompt)
        

    def _load_category_set(self, config_path, client):
        """
        从数据库加载指定client的类目集合，格式为["cate1-cate2", ...]
        :param config_path: 数据库配置文件路径
        :param client: 客户名
        :return: list[str]
        """
        connector = MySQLConnector(config_path)
        conn = connector.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            sql = "SELECT cate1, cate2 FROM data_content_category WHERE client = %s OR client = 'global_use'"
            cursor.execute(sql, (client,))
            result = []
            for row in cursor:
                try:
                    cate1 = row.get('cate1', '').strip()
                    cate2 = row.get('cate2', '').strip()
                    if cate1 and cate2:
                        result.append(f"{cate1}-{cate2}")
                except Exception as e:
                    continue

            return result
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"加载类目集合失败: {e}\n{tb}")
            logging.error(f'sql: {sql}')
            return []
        finally:
            connector.close_connection(conn, cursor)

    def batch_query_category(self, query_list, other_category=["其它"]):
        """
        批量对query进行分类，返回与query位置一一对应的category
        :param query_list: list[str]
        :param other_category: list[str]，可选，补充的其它类目
        :return: list[str]，与query_list顺序对应
        """
        if not query_list:
            return []
        # 组装dify输入
        query_list = [q.replace('\n', ' ').strip() for q in query_list]
        query_str = '\n'.join(query_list)
        category_str = '\n'.join(self.category_set + other_category)
        inputs = {
            'category_set': category_str
        }
        # dify模型调用
        result = self.dify_model.request_dify(query_str, other_inputs=inputs)
        if not result:
            return None
        # 解析结果，格式: query\tcategory\n...
        lines = result.strip().split('\n')
        query2cate = {}
        for line in lines:
            if '$$$' in line:
                q, c = line.split('$$$', 1)
                if c.strip() == '其他':
                    c = '其他'
                query2cate[q.strip()] = c.strip()
        # 保证顺序
        return [query2cate.get(q, "其它") for q in query_list]
