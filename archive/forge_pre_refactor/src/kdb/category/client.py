"""CategoryClient —— 类目服务数据接口（HTTP）。

复刻旧 `SearchDataInterface` 内嵌的类目能力（load_category_map_dict /
map_cate_name_to_id / get_category_parent_chain），抽成独立数据模块：
- `KnowledgeService.web_search` 用它做 `category_names` → `category_ids` 映射；
- 未配置 `service_url` 时所有方法安全降级（返回 None/[]），与旧实现
  `category_service_url=''` 时的行为一致——不发任何 HTTP 请求。

行为对齐来源：旧 `knowledge_interface_tools/search_index_data_interface.py`
的 `load_category_map_dict`(121-220) / `map_cate_name_to_id`(223-231) /
`get_category_parent_chain`(361-386)。
"""

import logging
import time
import traceback
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class CategoryClient:
    """类目树查询客户端（带按 client 的本地缓存与刷新间隔）。"""

    def __init__(self, service_url: str = "", update_interval: float = 36000) -> None:
        """
        Args:
            service_url: 类目服务 GET 接口（旧 config `category_service_url`）；空串=禁用（纯降级）。
            update_interval: 每个 client 类目字典的刷新间隔秒数（旧 `category_update_time_interval`）。
        """
        self.service_url = service_url or ""
        self.update_interval = update_interval
        self.all_client_category_dict: Dict[str, Dict[str, Any]] = {}
        self.category_update_time_dict: Dict[str, float] = {}

    def load_category_map_dict(self, client: str, user: Optional[str] = None):
        """拉取 client 的类目树并构造 name/id 反映射字典（与旧实现一致）。

        Returns:
            True: 加载成功；None: 命中缓存间隔 / 未配置 URL / 请求失败。
        """
        try:
            if (
                client in self.category_update_time_dict
                and time.time() - self.category_update_time_dict[client] < self.update_interval
            ):
                return
            if not self.service_url:
                return

            params = {"client": client}
            if user:
                params["user"] = user
            response = requests.get(self.service_url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()

            category_data = result.get("data", [])
            leaf_category_map_dict: Dict[str, Dict[str, Any]] = {
                "name_map_dict": {},
                "id_map_dict": {},
            }

            def traverse_category(node: Dict[str, Any], parent_chain: List[Dict[str, Any]]):
                category_id = node.get("categoryId")
                category_name = node.get("categoryName")
                level = node.get("level", 0)
                current_info = {
                    "category_name": category_name,
                    "category_id": category_id,
                    "level": level,
                }
                current_chain = parent_chain + [current_info]
                # name_map_dict 的 key 使用全路径（用"-"连接）；id_map_dict 用单一 ID
                if category_name:
                    category_path = "-".join(n["category_name"] for n in current_chain)
                    leaf_category_map_dict["name_map_dict"][category_path] = current_chain
                if category_id:
                    leaf_category_map_dict["id_map_dict"][category_id] = current_chain
                for child in node.get("children", []):
                    traverse_category(child, current_chain)

            for category in category_data:
                traverse_category(category, [])

            logger.info(
                "成功加载 client=%s 的类目字典，name_map 共 %d 项，id_map 共 %d 项",
                client,
                len(leaf_category_map_dict["name_map_dict"]),
                len(leaf_category_map_dict["id_map_dict"]),
            )
            self.category_update_time_dict[client] = time.time()
            self.all_client_category_dict[client] = leaf_category_map_dict
            return True

        except requests.RequestException as e:
            logger.error("请求类目服务失败: %s", e)
            return
        except Exception:
            logger.error("加载类目字典失败: %s", traceback.format_exc())
            return

    def map_cate_name_to_id(self, client: str, category_name: str):
        """类目全路径名 → 末级 category_id；未命中返回 None（与旧实现一致）。"""
        if category_name not in self.all_client_category_dict.get(client, {}).get(
            "name_map_dict", {}
        ):
            self.load_category_map_dict(client)
        nodes = (
            self.all_client_category_dict.get(client, {})
            .get("name_map_dict", {})
            .get(category_name, [])
        )
        if nodes:
            return nodes[-1]["category_id"]
        return None

    def get_category_parent_chain(
        self, client: str, cate_id: Optional[str] = None, cate_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """按 id 或全路径名取"根→当前"完整类目链；未命中允许强制加载一次再查。"""
        parent_chain: List[Dict[str, Any]] = []
        if not cate_id and not cate_name:
            return parent_chain
        client_dict = self.all_client_category_dict.get(client, {})
        if cate_id:
            parent_chain = client_dict.get("id_map_dict", {}).get(cate_id, [])
        elif cate_name:
            parent_chain = client_dict.get("name_map_dict", {}).get(cate_name, [])
        if parent_chain:
            return parent_chain
        self.load_category_map_dict(client)  # 允许进行一次加载
        client_dict = self.all_client_category_dict.get(client, {})
        if cate_id:
            parent_chain = client_dict.get("id_map_dict", {}).get(cate_id, [])
        elif cate_name:
            parent_chain = client_dict.get("name_map_dict", {}).get(cate_name, [])
        return parent_chain or []
