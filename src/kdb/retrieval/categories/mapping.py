from typing import Any
from typing import Dict
from typing import List
import logging
import requests
import time
import traceback

def load_category_map_dict(self, client: str, user=None) -> Dict[str, Any]:
    """
    加载类目字典
    Args:
        client: 客户端标识
        user: 用户标识(可选)
    Returns:
        Dict[str, Any]: 类目字典，包含name_map_dict和id_map_dict
    """
    try:
        if client in self.category_update_time_dict and time.time() - self.category_update_time_dict[client] < self.category_update_time_interval:
            return
        if not self.category_service_url:
            return

        # 构造请求参数（GET 请求通过 URL 参数传递）
        params = {"client": client}
        if user:
            params["user"] = user

        # 发送 GET 请求获取类目数据
        # 示例: GET http://127.0.0.1:8166/rufit-ai/intranet/knowledge/qaCategory/tree?client=rufit_demo
        response = requests.get(self.category_service_url, params=params, timeout=10)
        response.raise_for_status()

        result = response.json()

        # 检查响应状态
        if response.status_code != 200:
            logging.error(f"获取类目数据失败: {result.get('message', '未知错误')}")
            return {'name_map_dict': {}, 'id_map_dict': {}}

        # 获取类目数据
        category_data = result.get('data', [])

        # 构造反映射字典
        leaf_category_map_dict = {
            'name_map_dict': {},
            'id_map_dict': {}
        }

        def traverse_category(node: Dict[str, Any], parent_chain: List[Dict[str, Any]]):
            """
            递归遍历类目树，构造反映射字典
            Args:
                node: 当前类目节点
                parent_chain: 父节点链(包含所有祖先节点的信息，不包含当前节点)
            """
            # 获取当前节点信息
            category_id = node.get('categoryId')
            category_name = node.get('categoryName')
            level = node.get('level', 0)

            # 构建当前节点的信息
            current_info = {
                'category_name': category_name,
                'category_id': category_id,
                'level': level
            }

            # 构造包含当前节点的完整链（parent_chain + 当前节点）
            current_chain = parent_chain + [current_info]

            # 将当前节点及其完整链添加到字典中
            # current_chain 包含从根节点到当前节点的完整路径（包含自己）

            # name_map_dict 的 key 使用全路径（用"-"连接）
            if category_name:
                category_path = '-'.join([n['category_name'] for n in current_chain])
                leaf_category_map_dict['name_map_dict'][category_path] = current_chain

            # id_map_dict 的 key 仍然使用单一的 ID
            if category_id:
                leaf_category_map_dict['id_map_dict'][category_id] = current_chain

            # 获取子节点
            children = node.get('children', [])

            # 递归处理所有子节点
            for child in children:
                traverse_category(child, current_chain)

        # 遍历所有顶层类目
        for category in category_data:
            traverse_category(category, [])

        logging.info(f"成功加载client={client}的类目字典，"
                    f"name_map共{len(leaf_category_map_dict['name_map_dict'])}项，"
                    f"id_map共{len(leaf_category_map_dict['id_map_dict'])}项")
        self.category_update_time_dict[client] = time.time()
        self.all_client_category_dict[client] = leaf_category_map_dict
        return True

    except requests.RequestException as e:
        logging.error(f"请求类目服务失败: {str(e)}")
        return
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"加载类目字典失败: {tb}")
        return


def map_cate_name_to_id(self, client, category_name):
    """
    """
    if category_name not in self.all_client_category_dict.get(client, {}).get('name_map_dict', {}):
        self.load_category_map_dict(client)
    nodes = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(category_name, [])
    if nodes:
        return nodes[-1]['category_id']
    return None


def get_category_parent_chain(self, client: str, cate_id: str=None, cate_name: str=None) -> List[Dict[str, Any]]:
    """
    获取类目父节点链
    Args:
        client: 客户端标识
        cate_id: 类目ID
    Returns:
        List[Dict[str, Any]]: 类目父节点链
    """
    parent_chain = []
    if not cate_id and not cate_name:
        return parent_chain
    if cate_id:
        parent_chain = self.all_client_category_dict.get(client, {}).get('id_map_dict', {}).get(cate_id, [])
    elif cate_name:
        parent_chain = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(cate_name, [])
    if parent_chain:
        return parent_chain
    self.load_category_map_dict(client) # 允许进行一次加载
    if cate_id:
        parent_chain = self.all_client_category_dict.get(client, {}).get('id_map_dict', {}).get(cate_id, [])
    elif cate_name:
        parent_chain = self.all_client_category_dict.get(client, {}).get('name_map_dict', {}).get(cate_name, [])
    if parent_chain:
        return parent_chain
    return []
