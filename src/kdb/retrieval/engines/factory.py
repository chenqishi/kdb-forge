from elasticsearch import Elasticsearch
from kdb.retrieval.engines.es8_search_interface import EsSearchInterfaceES8
from kdb.retrieval.engines.providers.es7 import EsSearchInterfaceOri
from kdb.retrieval.engines.providers.opensearch2 import EsSearchInterfaceOpen
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
import json
import logging

_NON_CLIENT_EXTRA_PARAMS = {"auto_update_mapping", "recall_mode", "es_version", "ensure_index_on_init"}


RECALL_MODE_LEGACY = "legacy"


class EsSearchInterface(object):
    """ES搜索接口工厂类，根据版本信息自动选择对应的实现类"""

    def __init__(self,
                 hosts: Optional[List[str]] = None,
                 index_name: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 vector_fields: Optional[Dict[str, int]] = None,
                 config_path: Optional[str] = None,
                 extra_params: Optional[Dict[str, Any]] = None,
                 es_version: Optional[str] = None,
                 *, maintenance_mode: bool = False):
        """
        初始化ES搜索接口工厂类
        Args:
            hosts: ES服务器地址列表
            index_name: 索引名称
            username: 用户名
            password: 密码
            vector_fields: 向量字段配置，格式为 {field_name: dimension}
            config_path: 配置文件路径
            extra_params: 额外的ES客户端参数
            es_version: ES版本信息，可选值：'es7'（默认）、'opensearch2'
        """
        if config_path:
            config = json.load(open(config_path, 'r', encoding='utf-8'))
            hosts = hosts or config.get('hosts')
            index_name = index_name or config.get('index_name')
            username = username or config.get('username')
            password = password or config.get('password')
            vector_fields = vector_fields or config.get('vector_fields')
            extra_params = extra_params or config.get('extra_params', {})
            es_version = es_version or config.get('es_version')
            if es_version is None and isinstance(config.get('extra_params'), dict):
                es_version = config['extra_params'].get('es_version')
        if es_version is None and isinstance(extra_params, dict):
            es_version = extra_params.get('es_version')
        if maintenance_mode:
            # The maintenance caller must never create the configured default
            # index or auto-update a mapping just to count existing documents.
            extra_params = dict(extra_params or {})
            extra_params.update(ensure_index_on_init=False, auto_update_mapping=False,
                                max_retries=0, retry_on_timeout=False)
            index_name = index_name or "__maintenance__"
        # 如果没有指定版本，尝试自动检测
        if es_version is None:
            es_version = self._detect_es_version(hosts, username, password, extra_params)

        # 根据版本选择对应的实现类。显式 ES8 只接受 8.17 client，绝不让旧 ES7
        # auto-detect 或 script_score 路径静默接管。
        normalized_version = str(es_version).strip().lower()
        if normalized_version.startswith(('es8', 'elasticsearch8', '8.')):
            self._impl = EsSearchInterfaceES8(
                hosts=hosts,
                index_name=index_name,
                username=username,
                password=password,
                vector_fields=vector_fields,
                config_path=config_path,
                extra_params=extra_params,
            )
            es_version = 'es8.17'
        elif normalized_version.startswith('opensearch'):
            self._impl = EsSearchInterfaceOpen(
                hosts=hosts,
                index_name=index_name,
                username=username,
                password=password,
                vector_fields=vector_fields,
                config_path=config_path,
                extra_params=extra_params
            )
        else:  # 默认使用ES 7.x实现，保留现有行为
            self._impl = EsSearchInterfaceOri(
                hosts=hosts,
                index_name=index_name,
                username=username,
                password=password,
                vector_fields=vector_fields,
                config_path=config_path,
                extra_params=extra_params
            )

        # 保存版本信息
        if maintenance_mode:
            self._impl._maintenance_mode = True
        self.es_version = es_version
        logging.info(f"ES搜索接口已初始化，使用版本: {es_version}")

    def _detect_es_version(self, hosts: Optional[List[str]], username: Optional[str],
                          password: Optional[str], extra_params: Optional[Dict[str, Any]]) -> str:
        """
        自动检测ES版本
        Returns:
            str: 'es7' 或 'opensearch2'
        """
        try:
            # 设置临时ES客户端参数
            es_params = {
                'hosts': hosts,
                'timeout': 10,
                'max_retries': 1,
                'retry_on_timeout': True,
                'verify_certs': False,
            }

            if username and password:
                es_params['http_auth'] = (username, password)

            if extra_params:
                # auto_update_mapping 是本项目自定义配置，不是 ES 客户端参数，传进去会 TypeError
                es_params.update({k: v for k, v in extra_params.items() if k not in _NON_CLIENT_EXTRA_PARAMS})

            # 创建临时客户端进行版本检测
            temp_es = Elasticsearch(**es_params)
            es_info = temp_es.info()
            version_number = es_info["version"]["number"]


            # 检查是否为OpenSearch
            if "opensearch" in es_info.get("version", {}).get("distribution", "").lower():
                logging.info(f"检测到OpenSearch版本: {version_number}")
                return 'opensearch2'
            elif version_number.startswith("2."):
                logging.info(f"检测到ES 2.x版本: {version_number}，使用OpenSearch兼容模式")
                return 'opensearch2'
            else:
                logging.info(f"检测到ES版本: {version_number}，使用ES 7.x兼容模式")
                return 'es7'

        except Exception as e:

            if hosts is not None:

                hosts = ''.join(hosts)
                logging.warning(f"无法自动检测ES版本: {str(e)}，使用hosts 判断版本, hosts: {hosts}")
                if "on.aws" in hosts:
                    return 'opensearch2'
                else:
                    return 'es7'
            logging.warning(f"无法自动检测ES版本: {str(e)}，默认使用ES 7.x兼容模式, hosts: {hosts}, username: {username}, password: {password}, extra_params: {extra_params}")
            return 'es7'

    def __getattr__(self, name):
        """将所有方法调用委托给具体的实现类"""
        return getattr(self._impl, name)
