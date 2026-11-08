from elasticsearch import Elasticsearch
from kdb.retrieval.engines.es_count_utils import complete_count
from kdb.retrieval.engines.es_maintenance import EngineMaintenanceMixin
from kdb.retrieval.engines.providers.recall_settings import RECALL_MODE_DEFAULT
from kdb.retrieval.engines.providers.recall_settings import RECALL_MODE_DUAL
from kdb.retrieval.engines.providers.recall_settings import logger
from kdb.retrieval.engines.providers.es7 import EsSearchInterfaceOri
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union
import json
import logging
import traceback

class EsSearchInterfaceOpen(EngineMaintenanceMixin):
    """AWS OpenSearch 2.19检索接口实现类，支持多向量检索"""

    def count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool = False) -> int:
        """原生计数；统计服务可要求完整分片结果，不触发索引初始化。"""
        response = self.es.count(index=index_name, body={"query": query})
        return complete_count(response) if require_complete else int(response.get("count", 0))

    def update_by_query(self, index_name: str, query: Dict[str, Any],
                        update_fields: Dict[str, Any], requests_per_second: int = 500) -> Dict[str, Any]:
        """Use the existing shared native assignment implementation."""
        return EsSearchInterfaceOri.update_by_query(self, index_name, query, update_fields, requests_per_second)

    def __init__(self,
                 hosts: Optional[List[str]] = None,
                 index_name: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 vector_fields: Optional[Dict[str, int]] = None,
                 config_path: Optional[str] = None,
                 extra_params: Optional[Dict[str, Any]] = None):
        """
        初始化OpenSearch搜索接口
        Args:
            hosts: OpenSearch服务器地址列表
            index_name: 索引名称
            username: 用户名
            password: 密码
            vector_fields: 向量字段配置，格式为 {field_name: dimension}
            config_path: 配置文件路径
            extra_params: 额外的OpenSearch客户端参数
        """
        if config_path:
            config = json.load(open(config_path, 'r', encoding='utf-8'))
            hosts = hosts or config.get('hosts')
            index_name = index_name or config.get('index_name')
            username = username or config.get('username')
            password = password or config.get('password')
            vector_fields = vector_fields or config.get('vector_fields')
            extra_params = extra_params or config.get('extra_params', {})

        # auto_update_mapping 不是 ES 客户端参数，必须在传给 Elasticsearch() 之前摘出来
        extra_params = dict(extra_params or {})
        auto_update_mapping = bool(extra_params.pop('auto_update_mapping', False))
        recall_mode = extra_params.pop('recall_mode', RECALL_MODE_DEFAULT) or RECALL_MODE_DEFAULT
        ensure_index = bool(extra_params.pop('ensure_index_on_init', True))
        extra_params.pop('es_version', None)

        if not hosts:
            raise ValueError("hosts不能为空")
        if not index_name:
            raise ValueError("index_name不能为空")

        # 设置OpenSearch 2.19客户端参数
        es_params = {
            'hosts': hosts,
            'timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True,
            'verify_certs': False,  # 如果是自签名证书，设置为False
        }

        # OpenSearch使用http_auth进行认证
        if username and password:
            es_params['http_auth'] = (username, password)

        # 添加额外参数
        if extra_params:
            es_params.update(extra_params)

        # 初始化OpenSearch客户端
        self.es = Elasticsearch(**es_params)

        # 检查OpenSearch版本
        es_info = self.es.info()
        es_version = es_info["version"]["number"]
        if not es_version.startswith("2."):
            logging.warning(f"当前OpenSearch版本为 {es_version}，此接口针对OpenSearch 2.x优化，可能存在兼容性问题")

        self.index_name = index_name
        self.vector_fields = vector_fields or {}
        self.has_build_index = dict()
        # 是否允许对「已存在的索引」自动 put_mapping 补字段（配置项 extra_params.auto_update_mapping）。
        # 默认关：这个动作会在检索热路径上触发，实测会给线上 66 个索引加 categorys_info、
        # 59 个加 task_id/multimodal_contents、22 个加 dataset/primary_category；
        # 而 mapping 字段类型一旦写入就不可更改（例如 dataset 的 index:false 会让该字段永久不可检索）。
        # 新建索引不受影响，始终按完整 mapping 创建。
        self.auto_update_mapping = auto_update_mapping
        # 召回模式，见 RECALL_MODE_* 常量（配置项 extra_params.recall_mode，默认 legacy）
        self.recall_mode = recall_mode
        # 确保索引存在
        if ensure_index:
            self._ensure_index(index_name)

    def _ensure_index(self, index_name: str):
        """确保索引存在，使用OpenSearch 2.19推荐的索引设置，包含向量检索配置。
        同一进程内每个索引只检查一次——mapping 不兼容是永久性的，重试只会白白多打 ES 请求。
        """
        index_name = index_name.lower() # es只能用小写作为索引名
        if index_name in self.has_build_index:
            return
        try:
            # 获取第一个向量字段的维度
            vector_field_name = list(self.vector_fields.keys())[0]
            vector_dimension = self.vector_fields[vector_field_name]

            # 构建索引配置 - OpenSearch 2.19使用knn_vector而不是dense_vector
            new_mapping = {
                "properties": {
                    "title": {"type": "text", "analyzer": "ik_max_word"},
                    "synonyms_title": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "fields": {
                            "keyword": {
                                "type": "keyword",
                                "ignore_above": 256
                            }
                        }
                    },
                    "content": {"type": "text", "analyzer": "ik_max_word"},
                    "title_embedding": {  # OpenSearch 2.19支持向量索引
                        "type": "knn_vector",  # OpenSearch 2.19使用knn_vector
                        "dimension": vector_dimension,
                        "space_type": "cosinesimil"  # 使用余弦相似度
                    },
                    "content_embedding": {  # OpenSearch 2.19支持向量索引
                        "type": "knn_vector",  # OpenSearch 2.19使用knn_vector
                        "dimension": vector_dimension,
                        "space_type": "cosinesimil"  # 使用余弦相似度
                    },
                    "data_type": {"type": "keyword"},
                    "platform": {"type": "keyword"},
                    "dataset": {
                        "type": "keyword",
                        "index": False  # 不建索引，仅存储，dataset的名称，一般即为indexname， 之所以再存储，是因为为了适配所有dataset存在一个index中的情况
                    },
                    "audit_result": {"type": "integer"},  # 修改字段名，-1未审核，0审核不通过，1审核通过
                    "del_flag": {"type": "integer"}, # 新增字段，是否被删除
                    "quality_level": {  # 新增字段
                        "type": "keyword",
                        "normalizer": "lowercase"
                    },
                    "keywords": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "indexes": {
                        "type": "nested",
                        "properties": {
                            "text": {"type": "text", "analyzer": "ik_max_word"},
                            "embedding": {
                                "type": "knn_vector",  # OpenSearch 2.19使用knn_vector
                                "dimension": vector_dimension,
                                "space_type": "cosinesimil"  # 使用余弦相似度
                            }
                        }
                    },
                    "image_indexes": {
                        "type": "nested",
                        "properties": {
                            "text": {
                                "type": "text",
                                "index": True
                            },
                            "embedding": {
                                "type": "knn_vector",  # OpenSearch 2.19使用knn_vector
                                "dimension": vector_dimension,
                                "space_type": "cosinesimil"  # 使用余弦相似度
                            }
                        }
                    },
                    "insert_time": {
                        "type": "date",
                        "format": "yyyy-MM-dd HH:mm:ss"
                    },
                    "update_time": {
                        "type": "date",
                        "format": "yyyy-MM-dd HH:mm:ss"
                    },
                    "from_type": {  # 新增字段
                        "type": "keyword"
                    },
                    "from_type_norm": {  # 新增字段，用于存储from_type和from_file_name的规范化值
                        "type": "keyword"
                    },
                    "categorys_info": {  # 类目分类信息，不参与检索
                        "type": "object",
                        "enabled": False  # 不参与检索
                    },
                    "primary_category": {  # 主类目信息
                        "type": "object",
                        "properties": {
                            "category_path": {"type": "keyword"},  # 精确检索，不分词
                            "category_ids": {"type": "keyword"},
                            "cate1_name": {"type": "keyword"},
                            "cate1_id": {"type": "keyword"},
                            "cate2_name": {"type": "keyword"},
                            "cate2_id": {"type": "keyword"},
                            "cate3_name": {"type": "keyword"},
                            "cate3_id": {"type": "keyword"},
                            "cate_name": {"type": "keyword"}
                        }
                    },
                    "multimodal_contents": {  # 多模态内容列表，不参与检索
                        "type": "object",
                        "enabled": False  # 完全不索引，仅存储
                    },
                    "ext_info": {"type": "object"}
                }
            }

            if not self.es.indices.exists(index=index_name):
                # 创建新索引
                index_body = {
                    "settings": {
                        "index": {
                            "number_of_shards": 3,
                            "number_of_replicas": 1,
                            "refresh_interval": "30s",
                            "knn": True  # 启用knn功能
                        }
                    },
                    "mappings": new_mapping
                }
                self.es.indices.create(
                    index=index_name,
                    body=index_body
                )
            else:
                if not self.update_index_map(index_name, new_mapping):
                    logging.warning(f"索引 {index_name} 的mapping同步未完成，本进程不再重试；如需修正需删除索引后重建")
            # 检查过就记住：mapping 不兼容是永久性的，重复检查只是白跑 ES 请求。
            # 异常路径不置位，保留下次重建的机会。
            self.has_build_index[index_name] = True
        except Exception as e:
            logging.error(f"创建索引失败: {str(e)}, index_name: {index_name}")
            raise

    def update_index_map(self, index_name: str, new_mapping: Dict[str, Any]) -> bool:
        """更新索引的mapping配置，仅支持添加新字段，不支持修改已存在字段的配置"""
        try:
            index_name = index_name.lower()
            if not self.es.indices.exists(index=index_name):
                raise ValueError(f"索引 {index_name} 不存在")

            # 获取现有索引的mapping
            existing_mapping = self.es.indices.get_mapping(index=index_name)[index_name]['mappings']
            existing_properties = existing_mapping.get('properties', {})

            # 检查是否需要更新mapping
            fields_to_update = {}
            for field_name, field_config in new_mapping['properties'].items():
                if field_name not in existing_properties:
                    # 新字段，可以添加
                    fields_to_update[field_name] = field_config
                else:
                    # 检查字段配置是否有变化
                    existing_field = existing_properties[field_name]
                    for key, value in field_config.items():
                        if key == "index":
                            continue
                        if existing_field.get(key) != value:
                            raise ValueError(
                                f"字段 {field_name} 的配置发生变化。ES不支持修改已存在字段的mapping配置。\n"
                                f"现有配置: {json.dumps(existing_field, ensure_ascii=False, indent=2)}\n"
                                f"新配置: {json.dumps(field_config, ensure_ascii=False, indent=2)}\n"
                                f"no equal key: {key}, value: {value}, existing_value: {existing_field.get(key)}"
                            )

            # 如果有新字段需要添加
            if fields_to_update:
                if not self.auto_update_mapping:
                    logging.info(
                        f"索引 {index_name} 缺少字段 {list(fields_to_update.keys())}，"
                        f"但 auto_update_mapping 未开启，跳过 put_mapping"
                    )
                    return True
                try:
                    self.es.indices.put_mapping(
                        index=index_name,
                        body={"properties": fields_to_update}
                    )
                    logging.info(f"成功更新索引 {index_name} 的mapping，新增字段: {list(fields_to_update.keys())}")
                    return True
                except Exception as e:
                    logging.error(f"更新索引 {index_name} 的mapping失败: {str(e)}")
                    raise
            else:
                logging.info(f"索引 {index_name} 无需更新mapping")
                return True

        except Exception as e:
            logging.error(f"更新索引mapping失败: {str(e)}, index_name: {index_name}")
            return False

    def _get_index_name(self, index_names: Optional[Union[str, List[str]]] = None) -> str:
        """获取要操作的索引名"""
        if not index_names:
            final_index_name = self.index_name
        else:
            if isinstance(index_names, list):
                final_index_name = ','.join(index_names)
                name_list = index_names
            else:
                final_index_name = index_names
                # str 也可能是逗号分隔的多索引串，必须拆开后逐个检查
                name_list = index_names.split(',')
            for one_index_name in name_list:
                one_index_name = one_index_name.strip()
                # has_build_index 的 key 是小写（_ensure_index 内部会 lower），查询侧必须对齐
                if one_index_name and one_index_name.lower() not in self.has_build_index:
                    self._ensure_index(one_index_name)
        final_index_name = final_index_name.lower()
        return final_index_name

    def search(self,
               query: Optional[Dict[str, Any]] = None,
               size: int = 10,
               index_names: Optional[Union[str, List[str]]] = None) -> List[Dict[str, Any]]:
        """混合检索接口，支持文本查询、属性匹配和向量检索"""
        try:
            if not query:
                query = {}

            # 构建复合查询
            should_queries = []
            must_queries = []

            # 1. 处理时间范围限制
            for time_field in ['insert_time', 'update_time']:
                if time_field in query:
                    time_range = query[time_field]
                    if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                        range_query = {}
                        if time_range[0]:
                            range_query["gte"] = time_range[0]
                        if time_range[1]:
                            range_query["lte"] = time_range[1]
                        if range_query:
                            must_queries.append({"range": {time_field: range_query}})

            # 2. 处理属性硬匹配
            if "attribute" in query and query["attribute"]:
                for field, value in query["attribute"].items():
                    if field == "from_file_name":
                        field = "ext_info.from_file_name.keyword"
                    # 特殊字段映射：primary_category的子字段自动加上前缀
                    elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                   "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                        field = f"primary_category.{field}"

                    if isinstance(value, list) or field == "keywords":
                        # 限制terms查询的列表长度，避免超过Elasticsearch的maxClauseCount限制(1024)
                        MAX_TERMS_COUNT = 1000
                        if isinstance(value, list) and len(value) > MAX_TERMS_COUNT:
                            logging.warning(f"字段 {field} 的查询列表长度({len(value)})超过限制({MAX_TERMS_COUNT})，将被截断")
                            value = value[:MAX_TERMS_COUNT]
                        must_queries.append({"terms": {field: value}})
                    else:
                        must_queries.append({"term": {field: value}})

            # 如果attribute中没有指定del_flag，则添加del_flag等于0的条件
            attribute_dict = query.get("attribute", {})
            if "del_flag" not in attribute_dict:
                must_queries.append({
                    "term": {"del_flag": 0}
                })

            # 3. 处理文本查询
            if "query" in query and query["query"]:
                if len(query["query"]) > 1024:
                    logging.warning(f"query长度超过1024，将被截断")
                    query["query"] = query["query"][:1024]
                should_queries.extend([
                    {
                        "multi_match": {
                            "query": query["query"],
                            "fields": ["title^2", "content^1.5", "indexes.text"],
                            "type": "best_fields",
                            "tie_breaker": 0.3
                        }
                    },
                    {
                        "match": {
                            "synonyms_title": {
                                "query": query["query"],
                                "boost": 1.8
                            }
                        }
                    }
                ])

            # 4. 处理向量检索 - OpenSearch 2.19使用knn查询
            if "vector" in query and query["vector"]:
                vector_value = query["vector"]["value"]
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]

                if len(vector_value) != vector_dimension:
                    raise ValueError(f"向量维度必须为 {vector_dimension}")

                # 将向量查询添加到should_queries中，使其成为可选条件
                should_queries.append({
                    "knn": {
                        "indexes.embedding": {
                            "vector": vector_value,
                            "k": size
                        }
                    }
                })

            # 构建最终查询 - 与ES 7.x保持一致的逻辑
            # OpenSearch 2.19的knn查询自带评分，不需要function_score包装
            final_query = {
                "query": {
                    "bool": {
                        "must": must_queries if must_queries else [{"match_all": {}}],
                        "should": should_queries,
                        "minimum_should_match": 1 if should_queries else 0
                    }
                },
                "size": size
            }

            response = self.es.search(
                index=self._get_index_name(index_names),
                body=final_query
            )

            results = [
                {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                for hit in response["hits"]["hits"]
            ]

            return results

        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"混合检索失败: {str(e)}, error query: {final_query}")
            logging.error(f"traceback: {tb}")
            return []

    def insert(self, data: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None, refresh_imm: bool = False) -> bool:
        """插入数据"""
        try:
            if '_id' not in data:
                raise ValueError("数据必须包含_id字段")

            # 获取第一个向量字段的维度
            vector_field_name = list(self.vector_fields.keys())[0]
            vector_dimension = self.vector_fields[vector_field_name]

            # 如果存在indexes字段，验证其格式和向量维度
            if 'indexes' in data:
                if not isinstance(data['indexes'], list):
                    raise ValueError("indexes字段必须是数组类型")

                # 过滤掉零向量
                valid_indexes = []
                for idx in data['indexes']:
                    if not isinstance(idx, dict):
                        raise ValueError("indexes数组的每个元素必须是字典类型")
                    if 'embedding' not in idx:
                        raise ValueError("每个索引必须包含embedding字段")
                    if 'text' not in idx:
                        raise ValueError("每个索引必须包含text字段")

                    # 验证向量维度
                    if len(idx['embedding']) != vector_dimension:
                        raise ValueError(f"每个索引的embedding维度必须为{vector_dimension}")

                    # 检查是否为零向量
                    if not all(v == 0 for v in idx['embedding']):
                        valid_indexes.append(idx)
                    else:
                        logging.warning(f"跳过零向量索引: {idx['text']}")

                # 更新indexes字段
                if valid_indexes:
                    data['indexes'] = valid_indexes
                else:
                    data.pop('indexes', None)
                    logging.warning("所有向量都是零向量，移除indexes字段")

            doc_id = data.pop('_id')
            result = self.es.update(
                index=self._get_index_name(index_names),
                id=doc_id,
                body={
                    "doc": data,
                    "doc_as_upsert": True
                },
                refresh=refresh_imm
            )
            logger.info(f"title:{data.get('title')}，_id:{doc_id}，插入数据结果: {result}, refresh_imm: {refresh_imm}")

            # 如果设置了立即刷新，额外强制刷新索引以确保查询能看到最新数据
            if refresh_imm:
                try:
                    self.es.indices.refresh(index=self._get_index_name(index_names))
                    logger.info(f"强制刷新索引完成: {self._get_index_name(index_names)}")
                except Exception as e:
                    logger.warning(f"强制刷新索引失败: {str(e)}")

            return result['result'] in ['created', 'updated']
        except Exception as e:
            logging.error(f"插入数据失败: {str(e)}")
            return False

    def update(self, data_id: str, data: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None) -> bool:
        """更新数据"""
        try:
            result = self.es.update(
                index=self._get_index_name(index_names),
                id=data_id,
                body={"doc": data}
            )
            return result['result'] == 'updated'
        except Exception as e:
            logging.error(f"更新数据失败: {str(e)}")
            return False

    def delete(self,
               data_id: str,
               index_names: Optional[Union[str, List[str]]] = None,
               refresh: bool = False) -> bool:
        """删除数据"""
        try:
            result = self.es.delete(
                index=self._get_index_name(index_names),
                id=data_id,
                refresh=refresh
            )
            return result['result'] == 'deleted'
        except Exception as e:
            logging.error(f"删除数据失败: {str(e)}")
            return False

    def get(self,
            data_id: str,
            index_names: Optional[Union[str, List[str]]] = None) -> Optional[Dict[str, Any]]:
        """根据ID获取数据"""
        try:
            result = self.es.get(
                index=self._get_index_name(index_names),
                id=data_id
            )
            return {"_id": result["_id"], **result["_source"]}
        except Exception as e:
            logging.error(f"获取数据失败: {str(e)}")
            return None

    # 为了保持接口一致性，添加其他方法的占位符
    def update_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
        """批量更新索引中满足条件的文档的指定字段值"""
        # 实现与EsSearchInterfaceOri相同
        return EsSearchInterfaceOri.update_value(self, index_name, update_value_dict, conditions)

    def insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]]) -> bool:
        """插入数据及其对应的多个向量"""
        return EsSearchInterfaceOri.insert_with_vectors(self, data, vectors)

    def search_by_vector(self, query_vector: List[float], vector_field: str, size: int = 10,
                        min_score: float = 0.0, return_score: bool = False,
                        extra_query: Optional[Dict[str, Any]] = None,
                        index_names: Optional[Union[str, List[str]]] = None) -> Union[List[Dict[str, Any]], List[Tuple]]:
        """
        通过向量相似度搜索数据 - OpenSearch 2.19实现
        Args:
            query_vector: 查询向量
            vector_field: 要查询的向量字段名
            size: 返回结果数量
            min_score: 最小相似度阈值
            return_score: 是否返回相似度分数
            extra_query: 额外的查询条件
            index_names: 要搜索的索引名，可以是单个索引名或索引名列表
        Returns:
            List[Dict] 或 List[Tuple]: 搜索结果列表
        """
        try:
            if vector_field not in self.vector_fields:
                raise ValueError(f"未知的向量字段: {vector_field}")
            if len(query_vector) != self.vector_fields[vector_field]:
                raise ValueError(f"查询向量维度必须为 {self.vector_fields[vector_field]}")

            # 构建基础查询条件，添加del_flag过滤
            must_filters = []

            # 处理额外查询条件
            if extra_query:
                if "attribute" in extra_query:
                    for field, value in extra_query["attribute"].items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                            field = f"primary_category.{field}"

                        if isinstance(value, list) or field == "keywords":
                            must_filters.append({"terms": {field: value}})
                        else:
                            must_filters.append({"term": {field: value}})

            # 如果没有指定del_flag，则添加del_flag等于0的条件
            attribute_dict = extra_query.get("attribute", {}) if extra_query else {}
            if "del_flag" not in attribute_dict:
                must_filters.append({
                    "term": {"del_flag": 0}
                })

            # 构建查询 - OpenSearch 2.19使用knn查询
            if must_filters:
                # 使用OpenSearch 2.19 knn查询，将向量查询作为should条件
                query = {
                    "query": {
                        "bool": {
                            "must": must_filters,
                            "should": [
                                {
                                    "knn": {
                                        vector_field: {
                                            "vector": query_vector,
                                            "k": size
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": size,
                    "min_score": min_score
                }
            else:
                # 纯向量查询
                query = {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "knn": {
                                        vector_field: {
                                            "vector": query_vector,
                                            "k": size
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": size,
                    "min_score": min_score
                }

            response = self.es.search(
                index=self._get_index_name(index_names),
                body=query
            )

            results = []
            for hit in response["hits"]["hits"]:
                if return_score:
                    results.append((
                        {"_id": hit["_id"], **hit["_source"]},
                        hit["_score"]
                    ))
                else:
                    results.append({"_id": hit["_id"], **hit["_source"]})

            return results
        except Exception as e:
            logging.error(f"向量检索失败: {str(e)}")
            return []

    def search_multi(self, query: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None,
                    size: int = 10, page_num: int = 1) -> List[Dict[str, Any]]:
        """
        支持多组属性条件的混合检索接口 - OpenSearch 2.19实现
        Args:
            query: 查询条件，格式如下：
                {
                    "query": "文本查询",
                    "vector": {"value": [...]},
                    "attribute": [  # 属性条件列表，列表间是OR关系
                        {  # 条件组1
                            "field1": value1,
                            "field2": value2
                        },
                        {  # 条件组2
                            "field1": value3,
                            "field2": value4
                        }
                    ]
                }
            size: 返回结果数量
            index_names: 要搜索的索引名
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            if not query:
                query = {}

            # 构建复合查询
            should_queries = []
            must_queries = []

            # 1. 处理时间范围限制
            for time_field in ['insert_time', 'update_time']:
                if time_field in query:
                    time_range = query[time_field]
                    if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                        range_query = {}
                        if time_range[0]:
                            range_query["gte"] = time_range[0]
                        if time_range[1]:
                            range_query["lte"] = time_range[1]
                        if range_query:
                            must_queries.append({"range": {time_field: range_query}})

            # 2. 处理属性硬匹配，支持多组条件
            has_del_flag = False
            if "attribute" in query and query["attribute"]:
                attribute_groups = query["attribute"]
                if isinstance(attribute_groups, list):
                    # 多组条件，每组之间是OR关系
                    attribute_queries = []
                    for attr_group in attribute_groups:
                        group_must = []
                        if "del_flag" in attr_group:
                            has_del_flag = True
                        for field, value in attr_group.items():
                            # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                            if field == "from_file_name":
                                field = "ext_info.from_file_name.keyword"
                            # 特殊字段映射：primary_category的子字段自动加上前缀
                            elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                                field = f"primary_category.{field}"

                            if field == "keywords" or isinstance(value, list):
                                group_must.append({
                                    "terms": {
                                        field: value if isinstance(value, list) else [value]
                                    }
                                })
                            else:
                                group_must.append({
                                    "term": {field: value}
                                })
                        if group_must:
                            attribute_queries.append({
                                "bool": {
                                    "must": group_must
                                }
                            })
                    if attribute_queries:
                        must_queries.append({
                            "bool": {
                                "should": attribute_queries,
                                "minimum_should_match": 1
                            }
                        })
                else:
                    # 单组条件，保持原有逻辑
                    if "del_flag" in attribute_groups:
                        has_del_flag = True
                    for field, value in attribute_groups.items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                            field = f"primary_category.{field}"

                        if field == "keywords" or isinstance(value, list):
                            must_queries.append({
                                "terms": {
                                    field: value if isinstance(value, list) else [value]
                                }
                            })

                        else:
                            must_queries.append({
                                "term": {field: value}
                            })

            # 如果attribute中没有指定del_flag，则添加del_flag等于0的条件
            if not has_del_flag:
                must_queries.append({
                    "term": {"del_flag": 0}
                })

            # 3. 处理文本查询 - 支持单个查询或多个查询列表
            if "query" in query and query["query"]:
                query_list = query["query"] if isinstance(query["query"], list) else [query["query"]]
                for q_text in query_list:
                    if q_text:  # 跳过空字符串
                        should_queries.extend([
                            {
                                "multi_match": {
                                    "query": q_text,
                                    "fields": ["title^2", "content^1.5", "indexes.text"],
                                    "type": "best_fields",
                                    "tie_breaker": 0.3
                                }
                            },
                            {
                                "match": {
                                    "synonyms_title": {
                                        "query": q_text,
                                        "boost": 1.8
                                    }
                                }
                            }
                        ])

            # 4. 处理向量检索 - OpenSearch 2.19使用knn查询，支持单个向量或多个向量列表
            if "vector" in query and query["vector"]:
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]

                # 支持两种格式：{"value": [...]} 或 [{"value": [...]}, ...]
                if isinstance(query["vector"], list):
                    # 多个向量的列表
                    vector_list = query["vector"]
                else:
                    # 单个向量（保持向后兼容）
                    vector_list = [query["vector"]]

                for vec_item in vector_list:
                    vector_value = vec_item["value"]

                    if len(vector_value) != vector_dimension:
                        raise ValueError(f"向量维度必须为 {vector_dimension}")

                    # 将向量查询添加到should_queries中，使其成为可选条件
                    should_queries.append({
                        "knn": {
                            "indexes.embedding": {
                                "vector": vector_value,
                                "k": size
                            }
                        }
                    })

            # 构建最终查询 - 与ES 7.x保持一致的逻辑
            # OpenSearch 2.19的knn查询自带评分，不需要function_score包装
            final_query = {
                "query": {
                    "bool": {
                        "must": must_queries if must_queries else [{"match_all": {}}],
                        "should": should_queries,
                        "minimum_should_match": 1 if should_queries else 0
                    }
                },
                "size": size
            }

            index_str = self._get_index_name(index_names)
            index_list = [s.strip() for s in index_str.split(',') if s.strip()]

            if len(index_list) <= 1:
                response = self.es.search(index=index_str, body=final_query)
                total_num = response["hits"]["total"]["value"]
                logging.info(f"检索语句: {final_query}")
                return [
                    {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    for hit in response["hits"]["hits"]
                ], total_num

            # 多索引：一次 msearch，各索引各返回 top size，总条数最多 index_num * size
            msearch_body = []
            for one_index in index_list:
                msearch_body.append({"index": one_index})
                msearch_body.append(final_query)
            response = self.es.msearch(body=msearch_body)
            result_list = []
            total_num = 0
            for i, resp in enumerate(response.get("responses", [])):
                if resp.get("error"):
                    logging.warning(f"msearch 子请求失败 index={index_list[i] if i < len(index_list) else '?'}: {resp.get('error')}")
                    continue
                hits = resp.get("hits", {}).get("hits", [])
                total_val = resp.get("hits", {}).get("total", {})
                total_num += total_val.get("value", total_val) if isinstance(total_val, dict) else total_val
                idx_name = index_list[i] if i < len(index_list) else ""
                for h in hits:
                    result_list.append({
                        "_index": h.get("_index", idx_name),
                        "_id": h["_id"],
                        "score": h["_score"],
                        **h["_source"]
                    })
            logging.info(f"检索语句: {final_query}")
            return result_list, total_num

        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"混合检索失败: {str(e)}")
            logging.error(f"traceback: {tb}")
            return [], 0

    def search_multi_by_page(self, query: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None,
                            size: int = 10, page_num: int = 1, score_threshold: Optional[float] = None) -> Tuple[List[Dict[str, Any]], int]:
        """
        支持分页的多组属性条件混合检索接口 - OpenSearch 2.19实现
        Args:
            query: 查询条件，格式如下：
                {
                    "query": "文本查询",
                    "vector": {"value": [...]},
                    "attribute": [  # 属性条件列表，列表间是OR关系
                        {  # 条件组1
                            "field1": value1,
                            "field2": value2
                        },
                        {  # 条件组2
                            "field1": value3,
                            "field2": value4
                        }
                    ]
                }
            size: 每页返回结果数量
            page_num: 页码（从1开始）
            index_names: 要搜索的索引名
            score_threshold: 分数阈值，仅在query或vector存在时生效
        Returns:
            Tuple[List[Dict[str, Any]], int]: (搜索结果列表, 总记录数)
        """
        try:
            if not query:
                query = {}

            # 计算分页偏移量
            from_offset = (page_num - 1) * size

            # 构建复合查询
            should_queries = []
            must_queries = []

            # 1. 处理时间范围限制
            for time_field in ['insert_time', 'update_time']:
                if time_field in query:
                    time_range = query[time_field]
                    if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                        range_query = {}
                        if time_range[0]:
                            range_query["gte"] = time_range[0]
                        if time_range[1]:
                            range_query["lte"] = time_range[1]
                        if range_query:
                            must_queries.append({"range": {time_field: range_query}})

            # 2. 处理属性硬匹配，支持多组条件
            has_del_flag = False
            if "attribute" in query and query["attribute"]:
                attribute_groups = query["attribute"]
                if isinstance(attribute_groups, list):
                    # 多组条件，每组之间是OR关系
                    attribute_queries = []
                    for attr_group in attribute_groups:
                        group_must = []
                        if "del_flag" in attr_group:
                            has_del_flag = True
                        for field, value in attr_group.items():
                            # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                            if field == "from_file_name":
                                field = "ext_info.from_file_name.keyword"
                            # 特殊字段映射：primary_category的子字段自动加上前缀
                            elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                                field = f"primary_category.{field}"

                            if field == "keywords" or isinstance(value, list):
                                group_must.append({
                                    "terms": {
                                        field: value if isinstance(value, list) else [value]
                                    }
                                })
                            else:
                                group_must.append({
                                    "term": {field: value}
                                })
                        if group_must:
                            attribute_queries.append({
                                "bool": {
                                    "must": group_must
                                }
                            })
                    if attribute_queries:
                        must_queries.append({
                            "bool": {
                                "should": attribute_queries,
                                "minimum_should_match": 1
                            }
                        })
                else:
                    # 单组条件，保持原有逻辑
                    if "del_flag" in attribute_groups:
                        has_del_flag = True
                    for field, value in attribute_groups.items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id",
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                            field = f"primary_category.{field}"

                        if field == "keywords" or isinstance(value, list):
                            must_queries.append({
                                "terms": {
                                    field: value if isinstance(value, list) else [value]
                                }
                            })

                        else:
                            must_queries.append({
                                "term": {field: value}
                            })

            # 如果attribute中没有指定del_flag，则添加del_flag等于0的条件
            if not has_del_flag:
                must_queries.append({
                    "term": {"del_flag": 0}
                })

            # 3. 处理文本查询
            if "query" in query and query["query"]:
                should_queries.extend([
                    {
                        "multi_match": {
                            "query": query["query"],
                            "fields": ["title^2", "content^1.5", "indexes.text"],
                            "type": "best_fields",
                            "tie_breaker": 0.3
                        }
                    },
                    {
                        "match": {
                            "synonyms_title": {
                                "query": query["query"],
                                "boost": 1.8
                            }
                        }
                    }
                ])

            # 4. 处理向量检索 - OpenSearch 2.19使用knn查询
            if "vector" in query and query["vector"]:
                vector_value = query["vector"]["value"]
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]

                if len(vector_value) != vector_dimension:
                    raise ValueError(f"向量维度必须为 {vector_dimension}")

                # 计算合理的k值：应该大于等于 from + size，以确保分页有足够的结果
                # 同时设置一个合理的上限，避免性能问题
                k_value = max(from_offset + size, 100)  # 至少100，或者from+size

                # 将向量查询添加到should_queries中，使其成为可选条件
                should_queries.append({
                    "knn": {
                        "indexes.embedding": {
                            "vector": vector_value,
                            "k": k_value
                        }
                    }
                })

            # 构建最终查询 - 与search_multi保持一致的逻辑
            # OpenSearch 2.19的knn查询自带评分，不需要function_score包装
            final_query = {
                "query": {
                    "bool": {
                        "must": must_queries if must_queries else [{"match_all": {}}],
                        "should": should_queries,
                        "minimum_should_match": 1 if should_queries else 0
                    }
                },
                "from": from_offset,
                "size": size
            }

            # 新增：在ES查询阶段加分数阈值
            if score_threshold is not None and ("query" in query or "vector" in query):
                final_query["min_score"] = score_threshold

            search_indexs = self._get_index_name(index_names)
            search_indexs = search_indexs.split(',')
            result_list = []
            total_num = 0
            for search_index in search_indexs:
                logging.info(f"分页混合检索查询条件: {final_query}")
                response = self.es.search(
                    index=search_index,
                    body=final_query
                )
                result_list_tmp = [
                    {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    for hit in response["hits"]["hits"]
                ]
                total_num_tmp = response["hits"]["total"]["value"]
                logging.info(f"分页混合检索索引: {search_index}, total_num: {total_num_tmp}")
                result_list.extend(result_list_tmp)
                total_num += total_num_tmp
                #if len(result_list) >= size: 中途打断无法获取准确的total_num
                #    break
                from_offset_tmp = max(0, from_offset -  total_num) # 或者len(result_list) + from_offset -  total_num
                final_query["from"] = from_offset_tmp
            if len(result_list) > size:
                result_list = result_list[:size]
            return result_list, total_num

        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"分页混合检索失败: {str(e)}")
            logging.error(f"traceback: {tb}")
            return [], 0

    def scroll_search(self, query: Dict[str, Any], batch_size: int = 1000, scroll_timeout: str = '5m',
                     index_names: Optional[Union[str, List[str]]] = None) -> Iterator[Dict[str, Any]]:
        """使用scroll API进行大规模数据检索"""
        return EsSearchInterfaceOri.scroll_search(self, query, batch_size, scroll_timeout, index_names)

    def search_after(self, query: Dict[str, Any], batch_size: int = 1000, sort_field: str = "_id",
                    index_names: Optional[Union[str, List[str]]] = None) -> Iterator[Dict[str, Any]]:
        """使用search_after进行大规模数据检索，保持排序"""
        return EsSearchInterfaceOri.search_after(self, query, batch_size, sort_field, index_names)

    def get_unique_values(self, index_name: str, field_name: str, size: int = 10000,
                         include_doc_count: bool = False, extra_query: Optional[Dict[str, Any]] = None) -> Union[List[str], List[Dict[str, Any]]]:
        """获取指定字段的唯一值集合"""
        return EsSearchInterfaceOri.get_unique_values(self, index_name, field_name, size, include_doc_count, extra_query)

    def get_field_statistics(self, index_name: str, field_name: str, extra_query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """获取字段的统计信息，包括唯一值数量和分布"""
        return EsSearchInterfaceOri.get_field_statistics(self, index_name, field_name, extra_query)
