from kdb.shared.config.private_values import private_value as _private_value
from typing import Dict, Any, List, Optional, Union, Tuple, Iterator
from elasticsearch import Elasticsearch
from .es8_search_interface import EsSearchInterfaceES8
from .es_count_utils import complete_count
from .es_maintenance import EngineMaintenanceMixin, run_native_update
import logging
import numpy as np
import json
import hashlib
import traceback
import time
logger = logging.getLogger(__name__)

# 比对 mapping 时要忽略的键。
# 线上是 ES 7.10.0，dense_vector 只支持 dims；index / similarity 是 7.16+/8.x 才有的参数，
# 写进 mapping 会被 ES 静默丢弃（实测所有索引的实际 mapping 都是 {"type":"dense_vector","dims":1024}）。
# 不忽略的话，代码里写的 "similarity": "cosine" 会让每个索引都被判成「配置发生变化」。
# 升级到 ES 8 / OpenSearch 时要重新审视这张表——那时这两个参数是真生效的。
_MAPPING_IGNORED_KEYS = {"index", "similarity"}

# extra_params 里属于本项目自身的配置项，不能透传给 Elasticsearch() 构造函数
_NON_CLIENT_EXTRA_PARAMS = {"auto_update_mapping", "recall_mode", "es_version", "ensure_index_on_init"}

# 召回模式
#   legacy: 一路融合召回，bool.should 里 BM25 子句与向量子句分数相加（改造前的行为）
#   dual  : BM25 一路 + 向量一路分别召回后合并去重
# 之所以要拆：BM25 分量级 26~107，cosine 分量级 0~1，实测向量子句对总分的贡献中位数只有 0.92%，
# 去掉它 top80 候选集重合度仍有 99% —— 融合模式下向量那一路等于没参与召回。
RECALL_MODE_LEGACY = "legacy"
RECALL_MODE_DUAL = "dual"
# 默认双路。要回退到改造前的融合召回，在 config_es_engine.json 里配
# "extra_params": {"recall_mode": "legacy"}
RECALL_MODE_DEFAULT = RECALL_MODE_DUAL

# dual 模式下 _source 排除这些字段：单条文档 _source 139803 字节里 97.5% 是向量，
# indexes[] 约占 71%。排掉后由 nested inner_hits 把本地重排真正需要的那几项补回来。
_LEAN_SOURCE_EXCLUDES = ["indexes.embedding", "image_indexes.embedding"]

# 分片被取消（task_cancelled_exception）时的重试次数与退避秒数。
# 这是阿里云 serverless ES 在负载下的瞬时现象，退避后重试基本都能成功，
# 详见 _search_with_shard_check。
_SHARD_RETRY_TIMES = 3
_SHARD_RETRY_BACKOFF = 0.5

# 单次 ES 请求超过这个 size 就拆批。size 与负载两个因素都真实存在：
#
# 1) 硬上限：集群静置（请求间隔 5s）时实测
#      size=100  4/4 成功 0.4s      size=500   3/4 成功 1.9s
#      size=2000 4/4 成功 5.6s      size=5000  0/4    size=10000 0/4
#    5000 以上是**必败**，重试多少次都没用——拆批是唯一出路。
# 2) 负载抖动：集群被压满时 size=500 也会 4/6 失败，而同期 size=2000/3000 反而 4/6 成功。
#    这一层由 _search_once_with_retry 的重试兜底。
#
# 所以取 500 而不是贴着 2000：既远离硬上限，单批耗时也短（~2s），
# 被取消的窗口小、重试代价低。拆批后每批各自带重试。
_SAFE_PAGE_BATCH = 500

_PAGE_SOURCE_EXCLUDES = [
    "indexes.embedding",
    "image_indexes.embedding",
    "title_embedding",
    "content_embedding",
]

# inner_hits 取分数最高的前几项，连同它们的 embedding 一起回传，再按 _nested.offset 塞回
# doc['indexes'] 的对应位置 —— 这样 doc 的结构与不做 _source 过滤时完全一致，
# 下游 _cal_title_similarity 不需要任何改动（它本来就有 `and index_info.get('embedding')` 判断，
# 没塞到 embedding 的项会被自动跳过）。
#
# 取 1 在数学上已经足够：_cal_title_similarity 要的是 max(cos(title_embedding), max{同义问法的cos})，
#   · top1 是 title  → 所有同义问法都 ≤ 它，而 title 那一分本来就由 title_embedding 算出，结果相同
#   · top1 是同义问法 → 它就是全局最大，结果相同
# 唯一漏算的情况是 image_indexes 的文本（写入时冗余进了 indexes）抢了第一且某个同义问法高于 title，
# 实测 40 条候选里这种情况 0 条。默认取 3 留余量，体积敏感时可以降到 1。
_INNER_HITS_SIZE = 3
_INNER_HITS_NAME = "best_index"

RECALL_ROUTE_BM25 = "bm25"
RECALL_ROUTE_VECTOR = "vector"


def _mapping_config_equal(expected: Any, existing: Any) -> bool:
    """
    判断代码期望的 mapping 配置与 ES 返回的实际配置是否等价。
    只检查 expected 里出现的键（子集语义），并忽略 ES 会静默丢弃的参数和可省略的默认值。
    Args:
        expected: 代码里定义的配置片段
        existing: indices.get_mapping 返回的对应片段，字段不存在时为 None
    Returns:
        bool: 等价为 True
    """
    if isinstance(expected, dict) and isinstance(existing, dict):
        for key, value in expected.items():
            if key in _MAPPING_IGNORED_KEYS:
                continue
            # object 是 ES 的默认类型，返回的 mapping 里不会回显 type
            if key == "type" and value == "object" and "type" not in existing:
                continue
            if not _mapping_config_equal(value, existing.get(key)):
                return False
        return True
    return expected == existing


class EsSearchInterfaceOri(EngineMaintenanceMixin):
    """阿里云ES检索接口实现类，支持多向量检索"""
    
    def __init__(self, 
                 hosts: Optional[List[str]] = None,
                 index_name: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None,
                 vector_fields: Optional[Dict[str, int]] = None,
                 config_path: Optional[str] = None,
                 extra_params: Optional[Dict[str, Any]] = None):
        """
        初始化ES搜索接口
        Args:
            hosts: ES服务器地址列表
            index_name: 索引名称
            username: 用户名
            password: 密码
            vector_fields: 向量字段配置，格式为 {field_name: dimension}
            config_path: 配置文件路径
            extra_params: 额外的ES客户端参数
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
        
        # 设置ES 7.x客户端参数
        es_params = {
            'hosts': hosts,
            'timeout': 30,
            'max_retries': 3,
            'retry_on_timeout': True,
            'verify_certs': False,  # 如果是自签名证书，设置为False
        }
        
        # ES 7.x使用http_auth进行认证
        if username and password:
            es_params['http_auth'] = (username, password)
        
        # 添加额外参数
        if extra_params:
            es_params.update(extra_params)
        
        # 初始化ES 7.x客户端
        self.es = Elasticsearch(**es_params)
        
        # 检查ES版本
        es_version = self.es.info()["version"]["number"]
        if not es_version.startswith("7."):
            logging.warning(f"当前ES版本为 {es_version}，此接口针对ES 7.x优化，可能存在兼容性问题")
        
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
        """确保索引存在，使用阿里云推荐的索引设置，包含向量检索配置。
        同一进程内每个索引只检查一次——mapping 不兼容是永久性的，重试只会白白多打 ES 请求。
        """
        index_name = index_name.lower() # es只能用小写作为索引名
        if index_name in self.has_build_index:
            return
        try:
            # 获取第一个向量字段的维度
            vector_field_name = list(self.vector_fields.keys())[0]
            vector_dimension = self.vector_fields[vector_field_name]
            
            # 构建索引配置
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
                    "title_embedding": {  # 新增字段，不参与检索
                        "type": "dense_vector",
                        "dims": vector_dimension,
                        "index": False  # 不创建索引，不参与检索
                    },
                    "content_embedding": {  # 新增字段，不参与检索
                        "type": "dense_vector",
                        "dims": vector_dimension,
                        "index": False  # 不创建索引，不参与检索
                    },
                    "data_type": {"type": "keyword"},
                    "platform": {"type": "keyword"},
                    "dataset": {
                        "type": "keyword",
                        "index": False  # 不建索引，仅存储，一般即为indexname
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
                                "type": "dense_vector",
                                "dims": vector_dimension,
                                "similarity": "cosine"  # 使用余弦相似度
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
                                "type": "dense_vector",
                                "dims": vector_dimension,
                                "index": True,
                                "similarity": "cosine"
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
                    "dataset": {
                        "type": "keyword",
                        "index": False  # 不建索引，仅存储，一般即为indexname
                    },
                    "task_id": {
                        "type": "keyword",
                        "index": True
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
                            "cate4_name": {"type": "keyword"},
                            "cate4_id": {"type": "keyword"}
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
                            "refresh_interval": "30s"
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
        """把代码定义的mapping与线上实际mapping比对：缺失字段补上，已存在但不一致的字段跳过并告警
        Args:
            index_name: 索引名称
            new_mapping: 新的mapping配置
        Returns:
            bool: 比对流程是否正常走完（有不兼容字段但已跳过也算 True）
        """
        try:
            index_name = index_name.lower()
            if not self.es.indices.exists(index=index_name):
                raise ValueError(f"索引 {index_name} 不存在")

            # 获取现有索引的mapping
            existing_mapping = self.es.indices.get_mapping(index=index_name)[index_name]['mappings']
            existing_properties = existing_mapping.get('properties', {})
            
            # 检查是否需要更新mapping
            fields_to_update = {}
            conflict_fields = []
            for field_name, field_config in new_mapping['properties'].items():
                if field_name not in existing_properties:
                    # 新字段，可以添加
                    fields_to_update[field_name] = field_config
                    continue
                # 已存在的字段：ES 不支持改 mapping，不一致只能记录并跳过，不能中断其余字段的新增
                existing_field = existing_properties[field_name]
                if not _mapping_config_equal(field_config, existing_field):
                    conflict_fields.append(field_name)
                    logging.debug(
                        f"索引 {index_name} 字段 {field_name} 的mapping与代码定义不一致，已跳过。"
                        f"代码定义: {json.dumps(field_config, ensure_ascii=False)}；"
                        f"线上实际: {json.dumps(existing_field, ensure_ascii=False)}"
                    )

            if conflict_fields:
                logging.warning(
                    f"索引 {index_name} 存在无法修改的字段: {conflict_fields}，已跳过（如需修正需删除索引后重建）"
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
                except Exception as e:
                    logging.error(f"更新索引 {index_name} 的mapping失败: {str(e)}")
                    return False
            else:
                logging.info(f"索引 {index_name} 无需新增mapping字段")
            return True

        except Exception as e:
            logging.error(f"更新索引mapping失败: {str(e)}, index_name: {index_name}")
            return False

    # ---------------- 按文件名删除知识：底层查询能力 ----------------

    def count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool = False) -> int:
        """按 query 统计条数。

        用 _count API 而不是 search+len(hits)：_count 不受 size 截断影响，
        在本集群（分片会被静默取消，详见 _search_with_shard_check）下更可靠。
        """
        resp = self.es.count(index=index_name, body={"query": query})
        if require_complete:
            return complete_count(resp)
        return int(resp.get("count", 0))

    def agg_terms(self, index_name: str, query: Dict[str, Any], field: str,
                  size: int = 1000,
                  sub_aggs: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """按 field 做 terms 聚合，返回 [{key, doc_count, sub: {...}}]。

        聚合同样不受 size 截断影响，是本功能统计文件名/类型分布的首选方式。
        """
        aggs: Dict[str, Any] = {"terms": {"field": field, "size": size}}
        if sub_aggs:
            aggs["aggs"] = sub_aggs
        body = {"size": 0, "query": query, "aggs": {"grp": aggs}}
        resp = self._search_with_shard_check(index_name, body)
        out = []
        for b in (resp.get("aggregations", {}).get("grp", {}) or {}).get("buckets", []):
            item = {"key": b.get("key"), "doc_count": b.get("doc_count", 0)}
            for k, v in b.items():
                if isinstance(v, dict) and "buckets" in v:
                    item.setdefault("sub", {})[k] = {
                        x.get("key"): x.get("doc_count", 0) for x in v["buckets"]
                    }
            out.append(item)
        return out

    def sample_by_query(self, index_name: str, query: Dict[str, Any], size: int = 10,
                        includes: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """取若干条样例供人工确认。size 很小，不会触发分片取消。"""
        body: Dict[str, Any] = {"query": query, "size": size}
        if includes:
            body["_source"] = {"includes": includes}
        resp = self._search_with_shard_check(index_name, body)
        return [dict(h.get("_source") or {}, _id=h.get("_id"))
                for h in resp.get("hits", {}).get("hits", [])]

    def update_by_query(self, index_name: str, query: Dict[str, Any],
                        update_fields: Dict[str, Any],
                        requests_per_second: int = 500) -> Dict[str, Any]:
        """按 query 批量更新字段（本功能用来写 del_flag=1）。

        用 update_by_query 而不是「先查 ID 再逐条更新」：后者要把成千上万条 hits
        拉回来，正是会被分片取消静默截断的用法，会导致「以为删完了其实漏了一批」。

        conflicts=proceed：并发写入造成的版本冲突不中断整批，冲突数在返回里体现。
        requests_per_second：限流，本集群对负载敏感（见 _search_with_shard_check）。
        """
        script_parts, params = [], {}
        for field, value in update_fields.items():
            pname = "new_%s" % field.replace(".", "_")
            script_parts.append("ctx._source.%s = params.%s" % (field, pname))
            params[pname] = value
        body = {
            "query": query,
            "script": {"source": "; ".join(script_parts), "params": params, "lang": "painless"},
        }
        request = dict(index=index_name, body=body, conflicts="proceed", refresh=True,
                       wait_for_completion=True, requests_per_second=requests_per_second)
        maintenance_options = getattr(self, "_maintenance_update_options", None)
        resp = (run_native_update(self.es, request, client_api=7, **maintenance_options)
                if maintenance_options else self.es.update_by_query(**request))
        return {
            "updated": resp.get("updated", 0),
            "total": resp.get("total", 0),
            "version_conflicts": resp.get("version_conflicts", 0),
            "failures": resp.get("failures", []),
        }

    def update_value(self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
        """
        批量更新索引中满足条件的文档的指定字段值
        Args:
            index_name: 索引名称
            update_value_dict: 要更新的字段和值的映射，格式为 {field_name: new_value}
            conditions: 查询条件列表，每个条件为 {field_name: value} 格式
        Returns:
            bool: 更新是否成功
        """
        try:
            if not update_value_dict:
                logging.warning("update_value_dict 为空，无需更新")
                return True
            
            # 构建查询条件
            must_queries = []
            
            # 处理查询条件
            for condition in conditions:
                for field, value in condition.items():
                    # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                    if field == "from_file_name":
                        field = "ext_info.from_file_name.keyword"
                    # 特殊字段映射：primary_category的子字段自动加上前缀
                    elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                   "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
                        field = f"primary_category.{field}"
                    
                    if isinstance(value, list) or field == "keywords":
                        must_queries.append({"terms": {field: value}})
                    else:
                        must_queries.append({"term": {field: value}})
            
            # 如果没有查询条件，则匹配所有文档
            if not must_queries:
                query = {"match_all": {}}
            else:
                query = {
                    "bool": {
                        "must": must_queries
                    }
                }
            
            # 构建更新脚本
            script_source_parts = []
            script_params = {}
            
            for field, value in update_value_dict.items():
                param_name = f"new_{field.replace('.', '_')}"
                script_source_parts.append(f"ctx._source.{field} = params.{param_name}")
                script_params[param_name] = value
            
            script_source = "; ".join(script_source_parts)
            
            # 使用update_by_query API进行批量更新
            update_body = {
                "query": query,
                "script": {
                    "source": script_source,
                    "params": script_params,
                    "lang": "painless"
                }
            }
            
            logging.info(f"执行批量更新，索引: {index_name}, 更新条件: {conditions}, 更新字段: {update_value_dict}")
            
            result = self.es.update_by_query(
                index=index_name.lower(),
                body=update_body,
                wait_for_completion=True,
                refresh=True
            )
            
            updated_count = result.get('updated', 0)
            logging.info(f"批量更新完成，更新了 {updated_count} 个文档")
            
            return True
            
        except Exception as e:
            logging.error(f"批量更新失败: {str(e)}")
            logging.error(f"索引: {index_name}, 条件: {conditions}, 更新字段: {update_value_dict}")
            return False
    def insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]]) -> bool:
        """
        插入数据及其对应的多个向量
        Args:
            data: 要插入的数据，必须包含_id字段
            vectors: 向量数据字典，key为字段名，value为向量值
        Returns:
            bool: 插入是否成功
        """
        try:
            if '_id' not in data:
                raise ValueError("数据必须包含_id字段")
            
            # 验证所有向量字段
            for field_name, vector in vectors.items():
                if field_name not in self.vector_fields:
                    raise ValueError(f"未知的向量字段: {field_name}")
                if len(vector) != self.vector_fields[field_name]:
                    raise ValueError(f"向量 {field_name} 维度必须为 {self.vector_fields[field_name]}")
            
            doc_id = data.pop('_id')
            # 将向量数据添加到文档中
            data.update(vectors)
            
            result = self.es.index(
                index=self.index_name,
                id=doc_id,
                document=data
            )
            return result['result'] in ['created', 'updated']
        except Exception as e:
            logging.error(f"插入数据和向量失败: {str(e)}")
            return False

    def _get_index_name(self, index_names: Optional[Union[str, List[str]]] = None) -> str:
        """
        获取要操作的索引名
        Args:
            index_names: 指定的索引名，可以是单个索引名或索引名列表
        Returns:
            str: 处理后的索引名字符串
        """
        if not index_names:
            final_index_name = self.index_name
        else:
            if isinstance(index_names, list):
                final_index_name = ','.join(index_names)
                name_list = index_names
            else:
                final_index_name = index_names
                # str 也可能是逗号分隔的多索引串，必须拆开——否则会拿 "a,b" 整串去 _ensure_index，
                # get_mapping("a,b") 的返回里没有 "a,b" 这个 key，mapping 同步会静默失败
                name_list = index_names.split(',')
            for one_index_name in name_list: # 确保索引存在
                one_index_name = one_index_name.strip()
                # has_build_index 的 key 是小写（_ensure_index 内部会 lower），查询侧必须对齐
                if one_index_name and one_index_name.lower() not in self.has_build_index:
                    self._ensure_index(one_index_name)
        final_index_name = final_index_name.lower() # es只能用小写作为索引名
        return final_index_name

    def search(self,
               query: Optional[Dict[str, Any]] = None,
               size: int = 10,
               index_names: Optional[Union[str, List[str]]] = None) -> List[Dict[str, Any]]:
        """
        混合检索接口，支持文本查询、属性匹配和向量检索
        Args:
            query: 查询条件，格式如下：
                {
                    "query": "文本查询",
                    "vector": {"value": [...]},
                    "attribute": {"field": value},
                    "insert_time": [start_time, end_time],  # 可选，插入时间范围
                    "update_time": [start_time, end_time]   # 可选，更新时间范围
                }
            size: 返回结果数量
            index_names: 要搜索的索引名，可以是单个索引名或索引名列表
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
                        if time_range[0]:  # start_time
                            range_query["gte"] = time_range[0]
                        if time_range[1]:  # end_time
                            range_query["lte"] = time_range[1]
                        if range_query:
                            must_queries.append({"range": {time_field: range_query}})
            
            # 2. 处理属性硬匹配
            if "attribute" in query and query["attribute"]:
                for field, value in query["attribute"].items():
                    # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                    if field == "from_file_name":
                        field = "ext_info.from_file_name.keyword"
                    # 特殊字段映射：primary_category的子字段自动加上前缀
                    elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                   "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id"]:
                        field = f"primary_category.{field}"
                    
                    if isinstance(value, list) or field == "keywords":
                        must_queries.append({"terms": {field: value}})
                    else:
                        must_queries.append({"term": {field: value}})
            
            # 如果attribute中没有指定del_flag，则添加del_flag等于0的条件
            attribute_dict = query.get("attribute", {})
            if "del_flag" not in attribute_dict: # delflag 放在es底层引擎中限制，是因为del_flag=1的文档是做不存在，因此直接底层排除，而不是业务层限制
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
                                "boost": 1.8  # 给同义标题一个较高的权重
                            }
                        }
                    }
                ])
            
            # 4. 处理向量检索
            if "vector" in query and query["vector"]:
                vector_value = query["vector"]["value"]
                # 获取第一个向量字段的维度
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]
                
                if len(vector_value) != vector_dimension:
                    raise ValueError(f"向量维度必须为 {vector_dimension}")
                
                should_queries.append({
                    "nested": {
                        "path": "indexes",
                        "query": {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'indexes.embedding')",
                                    "params": {"query_vector": vector_value}
                                }
                            }
                        }
                    }
                })
            
            # 构建最终查询
            final_query = {
                "query": {
                    "function_score": {
                        "query": {
                            "bool": {
                                "must": must_queries if must_queries else [{"match_all": {}}],
                                "should": should_queries,
                                "minimum_should_match": 1 if should_queries else 0
                            }
                        },
                        "score_mode": "max",
                        "boost_mode": "replace"
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

    def search_by_vector(self, 
                        query_vector: List[float],
                        vector_field: str,
                        size: int = 10,
                        min_score: float = 0.0,
                        return_score: bool = False,
                        extra_query: Optional[Dict[str, Any]] = None,
                        index_names: Optional[Union[str, List[str]]] = None) -> Union[List[Dict[str, Any]], List[Tuple]]:
        """
        通过向量相似度搜索数据
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
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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

            # 构建查询
            if must_filters:
                query = {
                    "query": {
                        "bool": {
                            "must": must_filters,
                            "should": [{
                                "knn": {
                                    "field": vector_field,
                                    "query_vector": query_vector,
                                    "k": 10, # 返回结果数量
                                    "num_candidates": 100 # 调优参数
                                }
                            }]
                        }
                    },
                    "size": size,
                    "min_score": min_score
                }
            else:
                query = {
                    "query": {
                        "knn": {
                            "field": vector_field,
                            "query_vector": query_vector,
                            "k": 10,
                            "num_candidates": 100
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

    def insert(self, data: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None, refresh_imm: bool = False) -> bool:
        """
        插入数据
        Args:
            data: 要插入的数据，必须包含_id字段，indexes字段可选
            index_names: 要操作的索引名，可以是单个索引名或索引名列表
            refresh_imm: 是否立即刷新索引，True时写入后立即生效可被检索，False时等待ES自动刷新
        Returns:
            bool: 插入是否成功
        """
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
            #result = self.es.index(
            #    index=self._get_index_name(index_names),
            #    id=doc_id,
            #    body=data
            #)
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
                    # 强制刷新索引
                    self.es.indices.refresh(index=self._get_index_name(index_names))
                    logger.info(f"强制刷新索引完成: {self._get_index_name(index_names)}")
                    
                    # 等待一小段时间确保刷新完成
                    #import time
                    #time.sleep(0.1)
                    
                except Exception as e:
                    logger.warning(f"强制刷新索引失败: {str(e)}")
            
            return result['result'] in ['created', 'updated']
        except Exception as e:
            logging.error(f"插入数据失败: {str(e)}")
            return False
    
    def update(self, data_id: str, data: Dict[str, Any], index_names: Optional[Union[str, List[str]]] = None) -> bool:
        """
        更新数据
        Args:
            data_id: 文档ID
            data: 更新的数据内容
            index_names: 要操作的索引名，可以是单个索引名或索引名列表
        Returns:
            bool: 更新是否成功
        """
        try:
            result = self.es.update(
                index=self._get_index_name(index_names),
                id=data_id,
                body={"doc": data}  # 在body中使用doc字段包装更新内容
            )
            return result['result'] == 'updated'
        except Exception as e:
            logging.error(f"更新数据失败: {str(e)}")
            return False
    
    def delete(self, 
               data_id: str,
               index_names: Optional[Union[str, List[str]]] = None,
               refresh: bool = False) -> bool:
        """
        删除数据
        Args:
            data_id: 文档ID
            index_names: 要操作的索引名，可以是单个索引名或索引名列表
            refresh: 是否立即刷新使删除立即生效
        Returns:
            bool: 删除是否成功
        """
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
        """
        根据ID获取数据
        Args:
            data_id: 文档ID
            index_names: 要查询的索引名，可以是单个索引名或索引名列表
        Returns:
            Optional[Dict]: 数据内容，不存在则返回None
        """
        try:
            result = self.es.get(
                index=self._get_index_name(index_names),
                id=data_id
            )
            return {"_id": result["_id"], **result["_source"]}
        except Exception as e:
            logging.error(f"获取数据失败: {str(e)}")
            return None
    
    def _build_es_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        将通用查询格式转换为ES查询格式
        Args:
            query: 通用格式的查询条件
        Returns:
            Dict: ES格式的查询条件
        """
        if "fields" in query:
            # 处理精确匹配的字段查询
            must_conditions = []
            for field, value in query["fields"].items():
                must_conditions.append({"match": {field: value}})
            return {"bool": {"must": must_conditions}}
        
        # 如果是其他格式的查询，直接返回
        return query.get("query", {"match_all": {}})

    def _build_nested_vector_clause(self, vector_value: List[float],
                                    with_inner_hits: bool = False,
                                    boost: Optional[float] = None,
                                    score_mode: Optional[str] = None) -> Dict[str, Any]:
        """
        构造 indexes 的 nested 向量打分子句。
        Args:
            vector_value: query 的向量
            with_inner_hits: 是否带 inner_hits（只回传分数最高的前 _INNER_HITS_SIZE 项的 text + 分数，
                             用于在 _source 排除 indexes[].embedding 后仍能算同义问法的相似度）
            boost: 传 0 时该子句不贡献父文档分数，但 inner_hits 照常产出——
                   BM25 那一路用它白拿 inner_hits 而不干扰 BM25 排序
            score_mode: nested 的聚合方式。不传时 ES 默认 avg——同义问法越多向量分被摊得越低
                        （实测 8 项时 max=1.0000 而 avg=0.8710）。legacy 模式保持默认以维持原行为，
                        dual 模式显式传 'max'，与本地重排 _cal_title_similarity 取 max 的口径对齐
        Returns:
            Dict: 完整的 {"nested": {...}} 子句
        """
        nested = {
            "path": "indexes",
            "query": {
                "script_score": {
                    "query": {"match_all": {}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'indexes.embedding')",
                        "params": {"query_vector": vector_value}
                    }
                }
            }
        }
        if score_mode:
            nested["score_mode"] = score_mode
        if boost is not None:
            nested["boost"] = boost
        if with_inner_hits:
            nested["inner_hits"] = {
                "name": _INNER_HITS_NAME,
                "size": _INNER_HITS_SIZE,
                # 带上 embedding：外层 _source 把 indexes.embedding 排掉了，这里只补回分数最高的几项
                "_source": {"includes": ["indexes.text", "indexes.embedding"]}
            }
        return {"nested": nested}

    @staticmethod
    def _restore_inner_embeddings(hit: Dict[str, Any], doc: Dict[str, Any]) -> None:
        """
        把 inner_hits 带回的 embedding 按 _nested.offset 塞回 doc['indexes'] 的对应项。

        dual 模式下 _source 排除了 indexes.embedding（占 _source 约 71% 体积），
        doc['indexes'] 里每一项只剩 text；这里只把分数最高的那几项的 embedding 补回去，
        使 doc 的结构与不做过滤时一致，下游按原逻辑消费即可。

        Args:
            hit: ES 返回的一条命中（含 inner_hits）
            doc: 已经从 hit['_source'] 摊平出来的结果字典，原地修改
        """
        inner = (hit.get("inner_hits") or {}).get(_INNER_HITS_NAME)
        if not inner:
            return
        indexes = doc.get("indexes")
        if not isinstance(indexes, list):
            return
        for h in inner.get("hits", {}).get("hits", []):
            offset = (h.get("_nested") or {}).get("offset")
            embedding = (h.get("_source") or {}).get("embedding")
            if embedding is None or not isinstance(offset, int):
                continue
            if 0 <= offset < len(indexes) and isinstance(indexes[offset], dict):
                indexes[offset]["embedding"] = embedding

    @staticmethod
    def _merge_index_embeddings(target: Dict[str, Any], other: Dict[str, Any]) -> None:
        """把 other['indexes'] 里的 embedding 按 text 补进 target['indexes'] 缺失的项。

        两路命中同一条文档时，各自的 indexes[] 文本相同（同一份 _source），
        但只有向量路那份经 inner_hits 带回了部分 embedding。这里按 text 对齐补齐，
        使保留下来的那份也能算出同义问法的向量相似度。已有 embedding 的项不覆盖。
        """
        t_idx = target.get("indexes")
        o_idx = other.get("indexes")
        if not isinstance(t_idx, list) or not isinstance(o_idx, list):
            return
        by_text = {
            ix.get("text"): ix.get("embedding")
            for ix in o_idx
            if isinstance(ix, dict) and ix.get("text") and ix.get("embedding")
        }
        if not by_text:
            return
        for ix in t_idx:
            if isinstance(ix, dict) and not ix.get("embedding"):
                emb = by_text.get(ix.get("text"))
                if emb:
                    ix["embedding"] = emb

    def search_multi(self, 
                    query: Dict[str, Any], 
                    index_names: Optional[Union[str, List[str]]] = None,                     
                    size: int = 10,                    
                    page_num: int = 1,
                    recall_mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        支持多组属性条件的混合检索接口。多索引时一次 msearch。
        legacy 模式各索引取 top size；dual 模式各索引分 BM25/向量两路各取 size//2 后合并去重，
        并用 _source 排除 indexes[].embedding、由 nested inner_hits 补回本地重排需要的分数。
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
            index_names: 要搜索的索引名（多个时逗号分隔或列表）
        Returns:
            Tuple[List[Dict], int]: (结果列表, 总命中数)
        """
        try:
            if not query:
                query = {}
            
            # 构建复合查询
            must_queries = []
            
            # 1. 处理时间范围限制
            for time_field in ['insert_time', 'update_time']:
                if time_field in query:
                    time_range = query[time_field]
                    if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                        range_query = {}
                        if time_range[0]:  # start_time
                            range_query["gte"] = time_range[0]
                        if time_range[1]:  # end_time
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
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
            
            # 3. BM25 一路：文本子句
            bm25_should = []
            if "query" in query and query["query"]:
                query_list = query["query"] if isinstance(query["query"], list) else [query["query"]]
                for q_text in query_list:
                    if q_text:  # 跳过空字符串
                        bm25_should.extend([
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

            # 4. 向量一路：nested 子句，支持单个向量或多个向量列表
            mode = recall_mode or self.recall_mode
            is_dual = (mode == RECALL_MODE_DUAL)
            vector_should = []
            if "vector" in query and query["vector"]:
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]

                # 支持两种格式：{"value": [...]} 或 [{"value": [...]}, ...]
                if isinstance(query["vector"], list):
                    vector_list = query["vector"]
                else:
                    vector_list = [query["vector"]]

                for vec_item in vector_list:
                    vector_value = vec_item["value"]
                    if len(vector_value) != vector_dimension:
                        raise ValueError(f"向量维度必须为 {vector_dimension}")
                    vector_should.append(self._build_nested_vector_clause(
                        vector_value, with_inner_hits=is_dual,
                        score_mode="max" if is_dual else None))

            base_bool = {"must": must_queries if must_queries else [{"match_all": {}}]}
            # 只有真的挂了 inner_hits 才能排 _source：否则 indexes[].embedding 被排掉又没人补回来，
            # 下游 _cal_title_similarity 的同义问法分会静默丢失
            lean_source = is_dual and bool(vector_should)

            def _wrap(should_clauses, body_size):
                """把 should 子句包成完整的查询体。
                外层 function_score 没有 functions、boost_mode=replace，实测对分数无影响
                （ES 在无 functions 时不套用 replace），保留只为与 legacy 行为逐字节一致。"""
                q_bool = dict(base_bool)
                q_bool["should"] = should_clauses
                q_bool["minimum_should_match"] = 1 if should_clauses else 0
                body = {
                    "query": {
                        "function_score": {
                            "query": {"bool": q_bool},
                            "score_mode": "max",
                            "boost_mode": "replace"
                        }
                    },
                    "size": body_size
                }
                if lean_source:
                    # indexes[].embedding 占 _source 约 71% 体积，本地重排真正要的那几项由 inner_hits 补回
                    body["_source"] = {"excludes": list(_LEAN_SOURCE_EXCLUDES)}
                return body

            if is_dual and vector_should and bm25_should:
                per_route = max(1, size // 2)
                # BM25 路不挂任何 nested 向量子句。
                # 曾经挂过一份 boost=0 的 nested 来白拿 inner_hits，但 boost 只清零它对父文档分的
                # 贡献，cosineSimilarity 照样全量执行 —— 等于把最贵的向量打分跑了两遍。
                # 实测去掉后：单请求 p50 1.56s→1.08s、并发4 吞吐 1.22→1.87 req/s、回传 13.9→9.3MB；
                # 代价是只被 BM25 路召回的文档拿不到 indexes[].embedding，
                # _cal_title_similarity 的同义问法分支归零、退化成只用 title_embedding。
                # 30 个真实 query 实测：只被 BM25 路召回的 1442 条里，真的掉分的只有 2 条（0.1%），
                # 最大掉 0.0117 分，top1 重合 100%、top10 重合 96%。
                # 原因是「某个同义问法跟 query 很像」的文档必然被向量路召回，那时 inner_hits 就有。
                route_bodies = [
                    (RECALL_ROUTE_BM25, _wrap(bm25_should, per_route)),
                    (RECALL_ROUTE_VECTOR, _wrap(vector_should, per_route)),
                ]
            else:
                # 只有文本或只有向量时拆路没有意义；legacy 也走这里，BM25 与向量子句分数相加
                route_bodies = [(None, _wrap(bm25_should + vector_should, size))]

            index_str = self._get_index_name(index_names)
            index_list = [s.strip() for s in index_str.split(',') if s.strip()]

            if len(index_list) <= 1 and len(route_bodies) == 1:
                # 与 msearch 分支一致：分片被取消时重试，重试不成也不抛错（线上主路，
                # 宁可结果不完整也要能继续答），只打 error 日志。
                response = self._single_search_with_retry(index_str, route_bodies[0][1])
                total_num = response["hits"]["total"]["value"]
                return [
                    {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    for hit in response["hits"]["hits"]
                ], total_num

            # 一次 msearch 发出 index_num * route_num 个子请求
            msearch_body = []
            plan = []
            for one_index in index_list:
                for route_name, body in route_bodies:
                    msearch_body.append({"index": one_index})
                    msearch_body.append(body)
                    plan.append((one_index, route_name))
            response = self._msearch_with_shard_check(msearch_body)

            merged = {}
            order = []
            route_stat = {}
            total_num = 0
            for i, resp in enumerate(response.get("responses", [])):
                idx_name, route_name = plan[i] if i < len(plan) else ("", None)
                if resp.get("error"):
                    logging.warning(f"msearch 子请求失败 index={idx_name} route={route_name}: {resp.get('error')}")
                    continue
                # 分片取消已在 _msearch_with_shard_check 里整批重试过；能走到这里说明
                # 重试完仍有子请求不完整。线上主路不中断检索（双路互为兜底），
                # 这里补一条带 index/route 的日志，便于定位是哪一路少召回。
                sub_shards = resp.get("_shards") or {}
                if sub_shards.get("failed"):
                    logging.warning(
                        f"msearch 子请求分片被取消（重试后仍不完整） index={idx_name} route={route_name} "
                        f"failed={sub_shards.get('failed')}/{sub_shards.get('total')}"
                    )
                total_val = resp.get("hits", {}).get("total", {})
                sub_total = total_val.get("value", total_val) if isinstance(total_val, dict) else total_val
                # legacy 逐个累加；dual 时两路命中的是同一批数据，累加会重复计数，取最大值
                total_num = (total_num + sub_total) if route_name is None else max(total_num, sub_total)
                for h in resp.get("hits", {}).get("hits", []):
                    key = (h.get("_index", idx_name), h["_id"])
                    doc = {
                        "_index": h.get("_index", idx_name),
                        "_id": h["_id"],
                        "score": h["_score"],
                        **h["_source"]
                    }
                    self._restore_inner_embeddings(h, doc)
                    if key in merged:
                        # 两路都召回同一条：不二选一，而是**把两份合并**——
                        # 保留先到的那份（分数/排序位置不变），只把它缺的
                        # indexes[].embedding 从另一份补进去。
                        #
                        # 为什么不按 _score 择优：BM25 分量级 30~60、cosine 分量级 0~2，
                        # 不同量纲不可比，取 max 恒选 BM25；而最终排序本来就由本地
                        # _cal_similarity 决定，ES 分只用于截断候选。
                        #
                        # 为什么必须补 embedding：BM25 路自 bd4dae6 起不挂 nested 向量子句，
                        # 其 _source 又排除了 indexes[].embedding 且没有 inner_hits 可补
                        # （title_embedding/content_embedding 仍在，只缺 indexes 里的）。
                        # 而 _cal_title_similarity 的同义问法分支要求
                        # `text in synonyms_title and index_info.get('embedding')`，
                        # 拿不到 embedding 就整段空转、静默退化成只用 title_embedding。
                        # 先到先得会让 BM25 那份占坑，于是一条同义问法与 query 逐字相同
                        # (cosine=1.0) 的知识最终只得 title 的 0.648 分，排不进候选池
                        # （2026-09-07 wayfair「发货到…美国仓库…免租」线上答错即此因）。
                        self._merge_index_embeddings(merged[key], doc)
                        continue
                    merged[key] = doc
                    order.append(key)
                    route_stat[route_name or "legacy"] = route_stat.get(route_name or "legacy", 0) + 1
            if len(route_bodies) > 1:
                # 召回来源只进日志，不写进返回的文档——保持下游拿到的字段结构与 legacy 完全一致
                logging.info(f"dual召回: 各路新增 {route_stat}, 合并去重后 {len(order)} 条")
            return [merged[k] for k in order], total_num

        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"混合检索失败: {str(e)}")
            logging.error(f"traceback: {tb}")
            return [], 0

    def _single_search_with_retry(self, index_str: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """search_multi 的单索引单路分支：分片取消时重试，仍失败不抛错只记 error。"""
        for attempt in range(_SHARD_RETRY_TIMES):
            resp = self.es.search(index=index_str, body=body)
            shards = resp.get("_shards") or {}
            if not shards.get("failed"):
                if attempt:
                    logging.info(f"search 分片取消后重试成功: index={index_str} 第{attempt + 1}次")
                return resp
            logging.warning(f"search 分片被取消（结果不完整） index={index_str} "
                            f"failed={shards.get('failed')}/{shards.get('total')}，"
                            f"第{attempt + 1}/{_SHARD_RETRY_TIMES}次，准备重试")
            if attempt < _SHARD_RETRY_TIMES - 1:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        logging.error(f"search 重试 {_SHARD_RETRY_TIMES} 次后仍有分片被取消，本次召回不完整: index={index_str}")
        return resp

    def _msearch_with_shard_check(self, msearch_body: List[Dict[str, Any]]) -> Dict[str, Any]:
        """msearch + 分片取消重试（search_multi / 线上 /search 走这条）。

        msearch 的子请求被取消时同样不报 error，只在各自的 `_shards.failed` 留痕，
        表现为「这一路静默少召回」。这里按整批重试：只要有任一子请求分片失败就重发，
        退避后基本能成功。

        与单请求版的区别是重试仍失败时**不抛错**：这条是线上问答主路，
        双路召回互为兜底，宁可拿到不完整结果继续答，也不要整个检索挂掉；
        最终仍失败会打 error 日志，便于事后排查召回异常。
        """
        last_failed = None
        for attempt in range(_SHARD_RETRY_TIMES):
            resp = self.es.msearch(body=msearch_body)
            failed = []
            for i, sub in enumerate(resp.get("responses", [])):
                shards = sub.get("_shards") or {}
                if shards.get("failed"):
                    failed.append((i, shards.get("failed"), shards.get("total")))
            if not failed:
                if attempt:
                    logging.info(f"msearch 分片取消后重试成功: 第{attempt + 1}次")
                return resp
            last_failed = failed
            logging.warning(f"msearch 子请求分片被取消（结果不完整）: {failed}，"
                            f"第{attempt + 1}/{_SHARD_RETRY_TIMES}次，准备重试")
            if attempt < _SHARD_RETRY_TIMES - 1:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        logging.error(f"msearch 重试 {_SHARD_RETRY_TIMES} 次后仍有分片被取消，"
                      f"本次召回结果不完整: {last_failed}")
        return resp

    def _search_with_shard_check(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        '执行 ES 查询，并处理「分片被取消但仍返回 200」这一静默失败。\n\n        阿里云 serverless ES 会在负载压力下取消部分分片的查询任务，但整体仍返回\n        HTTP 200 + partial 结果，线索只在响应体里：\n            _shards: {total: 3, successful: 2, failed: 1,\n                      failures: [{shard: 0, reason: {type: "task_cancelled_exception"}}]}\n        此时 hits 可能是空的，而 hits.total 照旧报全量（如 9370）。调用方据此会得到\n        「total=9370 但一条都没有」，且完全不知道查询其实失败了——这是最危险的地方：\n        批量清洗类脚本会把「查不到」误判成「库里没有」。\n\n        注意这**不是**一个固定的 size 阈值问题。实测同一条 size=500 的请求连续成功\n        十几次后仍会偶发失败，失败率随并发/集群负载上升；size 越大只是概率越高。\n        所以这里用重试兜底（分片取消是瞬时现象，退避后重试基本都能成功），\n        而不是去拆批——拆批会成倍放大请求数，反而更容易触发取消。\n\n        重试仍失败则抛错，让调用方的 except 去兜，绝不静默返回空结果。\n\n        但重试救不了过大的 size：实测 size>=5000 时 5/5 全败，重试 3 次也全败——\n        那是集群真的扛不住，不是瞬时抖动。所以超过 _SAFE_PAGE_BATCH 的请求先拆批，\n        每批各自带重试。拆批本身会增加请求数，所以只在必要时才拆。\n        '
        size = body.get("size", 10)
        if size <= _SAFE_PAGE_BATCH:
            return self._search_once_with_retry(search_index, body)

        # 大 size 拆批：逐批顺序取，拼成与单次请求同构的响应
        from_offset = body.get("from", 0)
        merged_hits, total, max_score, took = [], None, None, 0
        fetched = 0
        while fetched < size:
            batch = min(_SAFE_PAGE_BATCH, size - fetched)
            sub = dict(body, **{"from": from_offset + fetched, "size": batch})
            resp = self._search_once_with_retry(search_index, sub)
            hits = resp["hits"]
            if total is None:
                total, max_score = hits.get("total"), hits.get("max_score")
            took += resp.get("took", 0)
            got = hits.get("hits") or []
            merged_hits.extend(got)
            fetched += batch
            if len(got) < batch:      # 这批没取满，后面不会再有
                break
        logging.info(f"分页大 size 拆批完成: index={search_index} size={size} 实得={len(merged_hits)}")
        return {"took": took,
                "hits": {"total": total if total is not None else {"value": len(merged_hits)},
                         "max_score": max_score, "hits": merged_hits}}

    def _search_once_with_retry(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """单次查询 + 分片取消重试。分片取消是瞬时现象，退避后重试基本都能成功。"""
        last_err = None
        for attempt in range(_SHARD_RETRY_TIMES):
            resp = self.es.search(index=search_index, body=body)
            shards = resp.get("_shards") or {}
            if not shards.get("failed"):
                if attempt:
                    logging.info(f"ES 分片取消后重试成功: index={search_index} 第{attempt + 1}次")
                return resp
            reasons = [f.get("reason", {}).get("type") for f in (shards.get("failures") or [])]
            last_err = (f"ES 分片查询失败（静默 200）: index={search_index} "
                        f"failed={shards.get('failed')}/{shards.get('total')} "
                        f"size={body.get('size')} from={body.get('from')} reasons={reasons}")
            logging.warning(f"{last_err}，第{attempt + 1}/{_SHARD_RETRY_TIMES}次，准备重试")
            if attempt < _SHARD_RETRY_TIMES - 1:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(f"{last_err}（已重试 {_SHARD_RETRY_TIMES} 次）")

    def search_multi_by_page(self,
                    query: Dict[str, Any],
                    index_names: Optional[Union[str, List[str]]] = None,                     
                    size: int = 10,                    
                    page_num: int = 1,
                    score_threshold: Optional[float] = None) -> Tuple[List[Dict[str, Any]], int]:
        """
        支持分页的多组属性条件混合检索接口
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
                        if time_range[0]:  # start_time
                            range_query["gte"] = time_range[0]
                        if time_range[1]:  # end_time
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
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
            
            # 4. 向量检索：本方法（/web_search 专用）刻意不做向量召回，只走 BM25。
            #
            # 原因是这里的 dense_vector 没有开 index（mapping 里只有 {"type":"dense_vector",
            # "dims":1024}，ES 7.10 下即「存而不建索引」），所以原来的 nested + script_score +
            # cosineSimilarity(match_all) 是一次全量暴力扫描：6 万文档 × 每条的每个 indexes 项
            # × 1024 维，每次查询都重算，根本吃不到索引。实测 ES 自己报的 took：
            #   from=0    size=10    仅BM25   39ms  vs 带向量  151ms
            #   from=9000 size=50    仅BM25   14ms  vs 带向量  351ms   (25x)
            #   from=9000 size=1000  仅BM25   11ms  vs 带向量 1569ms   (143x)
            # 翻页越深差距越大：BM25 能靠索引廉价跳过，script_score 却必须无差别重算全部。
            #
            # 而这条路拿掉向量不损失排序质量——它不做本地相似度重排（web_search_data 只
            # render_multimodal_urls + score 缩放），直接用 ES 打分。8 组真实 query 实测：
            # top1 全部相同，top10 重合 78/80，ES took 合计 1468ms -> 537ms。
            # 另外 script_score 内层是 match_all，会把每条文档都算作命中，白白撑大结果集
            # （n 从 6793 涨到 10000），也妨碍 BM25 的提前终止。
            #
            # 需要语义召回的是线上 /search 那条路（search_data_by_query -> search_multi），
            # 它有 dual 双路 + inner_hits + 本地重排，与本方法互不复用，不受此处影响。
            if "vector" in query and query["vector"]:
                vector_value = query["vector"]["value"]
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]
                # 维度照旧校验：调用方传错向量时行为不变（抛错），而不是被静默忽略
                if len(vector_value) != vector_dimension:
                    raise ValueError(f"向量维度必须为 {vector_dimension}")
            
            # 构建最终查询，添加分页参数
            final_query = {
                "query": {
                    "function_score": {
                        "query": {
                            "bool": {
                                "must": must_queries if must_queries else [{"match_all": {}}],
                                "should": should_queries,
                                "minimum_should_match": 1 if should_queries else 0
                            }
                        },
                        "score_mode": "max",
                        "boost_mode": "replace"
                    }
                },
                "from": from_offset,
                "size": size
            }

            # _source 排掉所有向量字段：本方法唯一的调用方是 web_search_data（/web_search），
            # 它不做本地相似度重排（只 render_multimodal_urls + score 缩放），而 /web_search
            # 出口处又会把所有含 "embedding" 的键过滤掉、indexes 只留 text —— 即这些向量
            # 传过来就是为了被丢弃。而单条 _source 里 97.5% 的体积是向量，size 又默认 10000，
            # 实测 size=1000 时 ES took 仅 620ms、墙钟却要 12.7s，瓶颈全在传输+反序列化。
            # 排掉后 12.7s -> 2.2s；size=10000 全字段则会直接把 ES 拖到 500 cancelled。
            # 注意：这里只裁 _source，不动 query 结构，向量召回那一路照常参与匹配和打分。
            final_query["_source"] = {"excludes": list(_PAGE_SOURCE_EXCLUDES)}

            # 新增：在ES查询阶段加分数阈值
            if score_threshold is not None and ("query" in query or "vector" in query):
                final_query["min_score"] = score_threshold

            search_indexs = self._get_index_name(index_names)
            search_indexs = search_indexs.split(',')
            result_list = []
            total_num = 0
            for search_index in search_indexs:
                logging.info(f"分页混合检索查询条件: {final_query}")
                response = self._search_with_shard_check(search_index, final_query)
                result_list_tmp = [
                    {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    for hit in response["hits"]["hits"]
                ]
                total_num_tmp = response["hits"]["total"]["value"]
                logging.info(f"分页混合检索索引: {search_index}, total_num: {total_num_tmp}") 
                result_list.extend(result_list_tmp)
                total_num += total_num_tmp
                #if len(result_list) >= size:  中途打断无法获取准确的total_num
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

    def scroll_search(self, 
                     query: Dict[str, Any], 
                     batch_size: int = 1000,
                     scroll_timeout: str = '5m',
                     index_names: Optional[Union[str, List[str]]] = None) -> Iterator[Dict[str, Any]]:
        """
        使用scroll API进行大规模数据检索
        Args:
            query: 查询条件，格式与search_multi相同
            batch_size: 每批次返回的数据量
            scroll_timeout: scroll上下文保持时间
            index_names: 要搜索的索引名
        Returns:
            Iterator[Dict[str, Any]]: 搜索结果迭代器
        """
        try:
            # 构建查询条件，复用search_multi的查询逻辑
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
                    attribute_queries = []
                    for attr_group in attribute_groups:
                        group_must = []
                        if "del_flag" in attr_group:
                            has_del_flag = True
                        for field, value in attr_group.items():
                            # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                            if field == "from_file_name":
                                field = "ext_info.from_file_name.keyword"
                            # 特殊字段映射：primary_category的子字段自动加上前缀
                            elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
                    if "del_flag" in attribute_groups:
                        has_del_flag = True
                    for field, value in attribute_groups.items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
            
            # 4. 处理向量检索
            if "vector" in query and query["vector"]:
                vector_value = query["vector"]["value"]
                vector_field_name = list(self.vector_fields.keys())[0]
                vector_dimension = self.vector_fields[vector_field_name]
                
                if len(vector_value) != vector_dimension:
                    raise ValueError(f"向量维度必须为 {vector_dimension}")
                
                should_queries.append({
                    "nested": {
                        "path": "indexes",
                        "query": {
                            "script_score": {
                                "query": {"match_all": {}},
                                "script": {
                                    "source": "cosineSimilarity(params.query_vector, 'indexes.embedding')",
                                    "params": {"query_vector": vector_value}
                                }
                            }
                        }
                    }
                })
            
            # 构建最终查询
            final_query = {
                "query": {
                    "bool": {
                        "must": must_queries if must_queries else [{"match_all": {}}],
                        "should": should_queries,
                        "minimum_should_match": 1 if should_queries else 0
                    }
                },
                "size": batch_size
            }
            logging.info(f"scroll检索查询条件: {final_query}")
            # 初始化scroll
            response = self.es.search(
                index=self._get_index_name(index_names),
                body=final_query,
                scroll=scroll_timeout
            )
            
            # 获取scroll_id
            scroll_id = response['_scroll_id']
            
            try:
                while True:
                    # 处理当前批次的结果
                    hits = response['hits']['hits']
                    if not hits:
                        break
                    
                    for hit in hits:
                        yield {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    
                    # 获取下一批结果
                    response = self.es.scroll(
                        scroll_id=scroll_id,
                        scroll=scroll_timeout
                    )
            
            finally:
                # 清理scroll上下文
                try:
                    self.es.clear_scroll(scroll_id=scroll_id)
                except Exception as e:
                    logging.warning(f"清理scroll上下文失败: {str(e)}")
            
        except Exception as e:
            tb = traceback.format_exc()
            logging.error(f"scroll检索失败: {str(e)}, error_query: {final_query}")
            
            logging.error(f"traceback: {tb}")
            yield from []

    def search_after(self, 
                    query: Dict[str, Any],
                    batch_size: int = 1000,
                    sort_field: str = "_id",
                    index_names: Optional[Union[str, List[str]]] = None) -> Iterator[Dict[str, Any]]:
        """
        使用search_after进行大规模数据检索，保持排序
        Args:
            query: 查询条件
            batch_size: 每批次返回的数据量
            sort_field: 排序字段，默认使用_id
            index_names: 要搜索的索引名
        Returns:
            Iterator[Dict[str, Any]]: 搜索结果迭代器
        """
        try:
            # 构建查询条件，与其他方法保持一致
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
                    attribute_queries = []
                    for attr_group in attribute_groups:
                        group_must = []
                        if "del_flag" in attr_group:
                            has_del_flag = True
                        for field, value in attr_group.items():
                            # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                            if field == "from_file_name":
                                field = "ext_info.from_file_name.keyword"
                            # 特殊字段映射：primary_category的子字段自动加上前缀
                            elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                           "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
                    if "del_flag" in attribute_groups:
                        has_del_flag = True
                    for field, value in attribute_groups.items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
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
            
            # 构建最终查询
            final_query = {
                "query": {
                    "bool": {
                        "must": must_queries if must_queries else [{"match_all": {}}],
                        "should": should_queries,
                        "minimum_should_match": 1 if should_queries else 0
                    }
                },
                "sort": [{sort_field: "asc"}],
                "size": batch_size
            }

            # 初始化search_after
            search_after = None
            
            while True:
                # 添加search_after参数
                if search_after:
                    final_query["search_after"] = search_after

                # 执行查询
                response = self.es.search(
                    index=self._get_index_name(index_names),
                    body=final_query
                )
                
                hits = response['hits']['hits']
                if not hits:
                    break
                    
                # 更新search_after值为最后一条记录的排序值
                search_after = hits[-1]['sort']
                
                # 返回当前批次的结果
                for hit in hits:
                    yield {"_id": hit["_id"], "score": hit["_score"], **hit["_source"]}
                    
        except Exception as e:
            logging.error(f"search_after检索失败: {str(e)}")
            yield from []
    
    def get_unique_values(self, 
                         index_name: str, 
                         field_name: str, 
                         size: int = 10000,
                         include_doc_count: bool = False,
                         extra_query: Optional[Dict[str, Any]] = None) -> Union[List[str], List[Dict[str, Any]]]:
        """
        获取指定字段的唯一值集合
        Args:
            index_name: 索引名称
            field_name: 字段名称
            size: 返回的唯一值数量限制（默认: 10000）
            include_doc_count: 是否包含每个值的文档数量（默认: False）
            extra_query: 额外的查询条件，用于过滤数据
        Returns:
            List[str] 或 List[Dict[str, Any]]: 唯一值列表，或包含值和文档数量的字典列表
        """
        try:
            # 构建基础查询
            query = {
                "size": 0,  # 不返回文档，只要聚合结果
                "aggs": {
                    "unique_vals": {
                        "terms": {
                            "field": field_name,
                            "size": size
                        }
                    }
                }
            }
            
            # 添加额外的查询条件
            if extra_query:
                must_conditions = []
                
                # 处理属性条件
                if "attribute" in extra_query:
                    for field, value in extra_query["attribute"].items():
                        # 特殊字段映射：from_file_name映射到ext_info.from_file_name.keyword（用于精确匹配）
                        if field == "from_file_name":
                            field = "ext_info.from_file_name.keyword"
                        # 特殊字段映射：primary_category的子字段自动加上前缀
                        elif field in ["category_path", "category_ids", "cate1_name", "cate1_id", 
                                       "cate2_name", "cate2_id", "cate3_name", "cate3_id", "cate_name"]:
                            field = f"primary_category.{field}"
                        
                        if isinstance(value, list) or field == "keywords":
                            must_conditions.append({"terms": {field: value}})
                        else:
                            must_conditions.append({"term": {field: value}})
                
                # 处理时间范围限制
                for time_field in ['insert_time', 'update_time']:
                    if time_field in extra_query:
                        time_range = extra_query[time_field]
                        if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                            range_query = {}
                            if time_range[0]:  # start_time
                                range_query["gte"] = time_range[0]
                            if time_range[1]:  # end_time
                                range_query["lte"] = time_range[1]
                            if range_query:
                                must_conditions.append({"range": {time_field: range_query}})
                
                # 默认添加del_flag=0的条件，除非明确指定了del_flag
                if "attribute" not in extra_query or "del_flag" not in extra_query["attribute"]:
                    must_conditions.append({"term": {"del_flag": 0}})
                
                # 如果有查询条件，添加到query中
                if must_conditions:
                    query["query"] = {
                        "bool": {
                            "must": must_conditions
                        }
                    }
            else:
                # 默认只查询未删除的文档
                query["query"] = {
                    "term": {"del_flag": 0}
                }
            
            # 执行聚合查询
            response = self.es.search(
                index=index_name.lower(),
                body=query
            )
            
            # 解析聚合结果
            if "aggregations" in response and "unique_vals" in response["aggregations"]:
                buckets = response["aggregations"]["unique_vals"]["buckets"]
                
                if include_doc_count:
                    # 返回包含文档数量的结果
                    return [
                        {
                            "value": bucket["key"],
                            "doc_count": bucket["doc_count"]
                        }
                        for bucket in buckets
                    ]
                else:
                    # 只返回唯一值
                    return [bucket["key"] for bucket in buckets]
            else:
                logging.warning(f"聚合查询结果中未找到 unique_vals: {response}")
                return []
                
        except Exception as e:
            logging.error(f"获取字段 {field_name} 唯一值失败: {str(e)}")
            traceback.print_exc()
            return []
    
    def get_field_statistics(self, 
                           index_name: str, 
                           field_name: str,
                           extra_query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取字段的统计信息，包括唯一值数量和分布
        Args:
            index_name: 索引名称
            field_name: 字段名称
            extra_query: 额外的查询条件
        Returns:
            Dict[str, Any]: 包含统计信息的字典
        """
        try:
            # 获取唯一值和文档数量
            unique_values = self.get_unique_values(
                index_name=index_name,
                field_name=field_name,
                include_doc_count=True,
                extra_query=extra_query
            )
            
            if not unique_values:
                return {
                    "field_name": field_name,
                    "unique_count": 0,
                    "total_docs": 0,
                    "values": []
                }
            
            # 计算总文档数和统计信息
            total_docs = sum(item["doc_count"] for item in unique_values)
            unique_count = len(unique_values)
            
            # 按文档数量排序
            sorted_values = sorted(unique_values, key=lambda x: x["doc_count"], reverse=True)
            
            return {
                "field_name": field_name,
                "unique_count": unique_count,
                "total_docs": total_docs,
                "top_values": sorted_values[:10],  # 前10个最常见的值
                "all_values": sorted_values
            }
            
        except Exception as e:
            logging.error(f"获取字段 {field_name} 统计信息失败: {str(e)}")
            return {
                "field_name": field_name,
                "error": str(e)
            }


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


def test_es_insert_and_create(file_path: str, 
                             hosts: Union[str, List[str]], 
                             username: str,
                             password: str):
    """
    测试ES的插入和创建操作
    Args:
        file_path: 数据文件路径
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},  # 假设使用默认768维向量
            index_name="test_knowledge"  # 使用测试索引名
        )
        
        # 读取并处理数据
        with open(file_path, 'r', encoding='utf-8') as f:
            index = 0
            for line in f:
                try:
                    # 解析原始数据
                    raw_data = json.loads(line.strip())
                    
                    # 生成文档ID
                    doc_id = hashlib.md5(line.strip().encode()).hexdigest()
                    embedding = [index * 0.01] * 1024
                    embedding[index] = 0.2
                    index += 1
                    # 转换为目标格式
                    doc_data = {
                        "_id": doc_id,  # 使用内容hash作为ID
                        "title": raw_data.get("title", ""),
                        "content": raw_data.get("content", ""),
                        "data_type": "qa",  # 根据数据格式判断为qa类型
                        "platform": raw_data.get("platform", ""),
                        "is_audit": 0,  # 默认未审核
                        "keywords": [],  # 暂时为空
                        "indexes": [
                            {
                                "text": raw_data.get("title", "") + " " + raw_data.get("content", ""),
                                "embedding": embedding
                            }
                        ],
                        "ext_info": {
                            "document_name": raw_data.get("document_name", "")
                        }
                    }
                    
                    # 插入数据
                    success = es_interface.insert(doc_data, refresh_imm=False)
                    if success:
                        print(f"成功插入数据: {doc_id}")
                    else:
                        print(f"插入数据失败: {doc_id}")
                        
                except json.JSONDecodeError:
                    print(f"解析JSON失败: {line.strip()}")
                except Exception as e:
                    print(f"处理数据失败: {str(e)}")
                    
    except Exception as e:
        print(f"测试失败: {str(e)}")

def test_search(hosts: str,
                username: str,
                password: str,
                index_name: str = "test_knowledge"):
    """
    测试ES的各种检索功能
    Args:
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
        index_name: 索引名称
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},
            index_name=index_name
        )
        
        # 1. 测试文本检索
        print("\n=== 测试文本检索 ===")
        text_query = {
            "query": "IOSS码",  # 文本查询
        }
        text_results = es_interface.search(text_query, size=5)
        print(f"文本检索结果数量: {len(text_results)}")
        for result in text_results:
            print(f"文档ID: {result['_id']}")
            print(f"标题: {result['title']}")
            print(f"内容: {result['content']}")
            print(f"相关度分数: {result['score']}\n")

        # 2. 测试向量检索
        print("\n=== 测试向量检索 ===")
        embedding = [0.01] * 1024
        embedding[3] = 0.2
        vector_query = {
            "vector": {
                "value": embedding
            }
        }
        vector_results = es_interface.search(vector_query, size=5)
        print(f"向量检索结果数量: {len(vector_results)}")
        for result in vector_results:
            print(f"文档ID: {result['_id']}")
            print(f"标题: {result['title']}")
            print(f"相似度分数: {result['score']}\n")

        # 3. 测试属性检索
        print("\n=== 测试属性检索 ===")
        attribute_query = {
            "attribute": {
                "platform": "RakutenFrance",
                "data_type": "qa",
                "is_audit": 0
            }
        }
        attribute_results = es_interface.search(attribute_query, size=5)
        print(f"属性检索结果数量: {len(attribute_results)}")
        for result in attribute_results:
            print(f"文档ID: {result['_id']}")
            print(f"平台: {result['platform']}")
            print(f"类型: {result['data_type']}")
            print(f"标题: {result['title']}\n")

        # 4. 测试混合检索
        print("\n=== 测试混合检索 ===")
        mixed_query = {
            "query": "IOSS码",
            "attribute": {
                "platform": "RakutenFrance"
            },
            "vector": {
                "value": embedding
            }
        }
        mixed_results = es_interface.search(mixed_query, size=5)
        print(f"混合检索结果数量: {len(mixed_results)}")
        for result in mixed_results:
            print(f"文档ID: {result['_id']}")
            print(f"平台: {result['platform']}")
            print(f"标题: {result['title']}")
            print(f"相关度分数: {result['score']}\n")

    except Exception as e:
        print(f"测试检索失败: {str(e)}")

def test_update(file_path: str, 
                hosts: Union[str, List[str]], 
                username: str,
                password: str):
    """
    测试ES的更新操作
    Args:
        file_path: 数据文件路径
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},
            index_name="test_knowledge"
        )
        
        # 读取并处理数据
        with open(file_path, 'r', encoding='utf-8') as f:
            index = 0
            for line in f:
                try:
                    # 解析原始数据
                    raw_data = json.loads(line.strip())
                    
                    # 生成文档ID
                    doc_id = hashlib.md5(line.strip().encode()).hexdigest()
                    embedding = [ 0.01] * 1024
                    embedding[index] = 0.2
                    index += 1
                    
                    # 转换为目标格式
                    doc_data = {
                        "title": raw_data.get("title", ""),
                        "content": raw_data.get("content", ""),
                        "data_type": "qa",
                        "platform": raw_data.get("platform", ""),
                        "is_audit": 0,
                        "keywords": [],
                        "indexes": [
                            {
                                "text": raw_data.get("title", "") + " " + raw_data.get("content", ""),
                                "embedding": embedding
                            }
                        ],
                        "ext_info": {
                            "document_name": raw_data.get("document_name", "")
                        }
                    }
                    
                    # 更新数据
                    success = es_interface.update(doc_id, doc_data)
                    if success:
                        print(f"成功更新数据: {doc_id}")
                    else:
                        print(f"更新数据失败: {doc_id}")
                        
                except json.JSONDecodeError:
                    print(f"解析JSON失败: {line.strip()}")
                except Exception as e:
                    print(f"处理数据失败: {str(e)}")
                    
    except Exception as e:
        print(f"测试失败: {str(e)}")

# 在主函数中添加测试调用
if __name__ == "__main__":
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.INFO, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    
    # ES配置
    ES_CONFIG = {
        "hosts": "http://for-kuajing-bot-a4d.public.cn-shenzhen.es-serverless.aliyuncs.com:9200",
        "username": "for-kuajing-bot-a4d",
        "password": _private_value('86eba6bfcdaf942a9797462b')
    }
    
    def search():
        """测试ES的各种检索功能"""
        ES_CONFIG["index_name"] = "test_knowledge"
        test_search(**ES_CONFIG)
    
    def insert(file_path: str):
        """
        测试ES的插入和创建操作
        Args:
            file_path: 数据文件路径
        """
        test_es_insert_and_create(file_path=file_path, **ES_CONFIG)
    
    def update(file_path: str):
        """
        测试ES的更新操作
        Args:
            file_path: 数据文件路径
        """
        test_update(file_path=file_path, **ES_CONFIG)
    
    # 使用fire注册命令
    fire.Fire({
        "search": search,
        "insert": insert,
        "update": update
    })
