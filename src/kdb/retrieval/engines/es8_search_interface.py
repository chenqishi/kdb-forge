"""Elasticsearch 8.17 CRUD and native vector retrieval engine.

The old project used the Elasticsearch 7 ``body=`` API and a brute-force
``script_score`` over an unindexed ``dense_vector``. This module is the
rebuild boundary: normal requests use Elasticsearch 8 named parameters and
vector retrieval uses an indexed HNSW ``dense_vector``.
"""

from __future__ import annotations

import copy
import logging
import math
import numbers
import time
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

from .es8_client_router import IndexClientRouter
from .es_count_utils import complete_count
from .es_maintenance import EngineMaintenanceMixin, run_native_update

logger = logging.getLogger(__name__)

IndexNames = Optional[Union[str, List[str]]]
_CATEGORY_FIELDS = {
    "category_path", "category_ids", "cate1_name", "cate1_id", "cate2_name",
    "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id", "cate_name",
}
_VECTOR_SOURCE_EXCLUDES = [
    "title_embedding", "content_embedding", "indexes.embedding", "image_indexes.embedding",
]
_LEAN_SOURCE_EXCLUDES = ["indexes.embedding", "image_indexes.embedding"]
_SHARD_RETRY_TIMES = 3
_SHARD_RETRY_BACKOFF = 0.5
_MSEARCH_MAX_CONCURRENT_SEARCHES = 2


def _split_index_names(index_names: IndexNames, default_index: str) -> List[str]:
    """将单索引、逗号分隔字符串或列表规范化为索引列表。"""
    value: Any = default_index if index_names is None else index_names
    names = value.split(",") if isinstance(value, str) else list(value)
    names = [str(name).strip().lower() for name in names if str(name).strip()]
    if not names:
        raise ValueError("index_name 不能为空")
    return names


def _as_dict(response: Any) -> Dict[str, Any]:
    """把 ES 8 ObjectApiResponse 或测试 double 统一成 dict。"""
    if isinstance(response, dict):
        return response
    body = getattr(response, "body", None)
    if isinstance(body, dict):
        return body
    try:
        return dict(response)
    except (TypeError, ValueError):
        return {}


def _response_value(response: Any, key: str, default: Any = None) -> Any:
    """读取 ES response 字段，兼容 dict 与 ES 8 response 对象。"""
    return _as_dict(response).get(key, default)


class EsSearchInterfaceES8(EngineMaintenanceMixin):
    """按 index 路由的 ES 8.17 引擎。

    类名保留是为了兼容上层 import，但生产实现已经不再实例化旧的
    ``EsSearchInterfaceOri``。跨 provider 的请求在本类分组，查询、mapping、
    CRUD 均使用 ES 8.17 API；dual 模式分别执行 BM25 与 native KNN 两路并去重。
    """

    def __init__(
        self,
        hosts: Optional[Union[str, List[str]]] = None,
        index_name: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vector_fields: Optional[Dict[str, int]] = None,
        config_path: Optional[str] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        *,
        config: Optional[Dict[str, Any]] = None,
        router: Optional[IndexClientRouter] = None,
        ensure_index: bool = True,
    ) -> None:
        """初始化 ES 8.17 路由引擎。"""
        if config is not None and config_path is not None:
            raise ValueError("config 与 config_path 只能指定一个")
        if config_path:
            import json

            with open(config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        config = dict(config or {})
        if router is None:
            if hosts is not None:
                config["hosts"] = hosts
            if username is not None:
                config["username"] = username
            if password is not None:
                config["password"] = password
            router = IndexClientRouter(config=config)
        self.router = router
        self.index_name = str(index_name or config.get("index_name") or "").strip().lower()
        if not self.index_name:
            raise ValueError("index_name 不能为空")
        self.vector_fields = dict(vector_fields or config.get("vector_fields") or {})
        if not self.vector_fields:
            raise ValueError("vector_fields 不能为空")
        configured_extra = dict(config.get("extra_params") or {})
        configured_extra.update(extra_params or {})
        self.auto_update_mapping = bool(configured_extra.get("auto_update_mapping", False))
        self.recall_mode = str(configured_extra.get("recall_mode", "dual") or "dual").lower()
        self.es_version = str(config.get("es_version") or "8.17")
        if not self.es_version.startswith("8.17"):
            raise ValueError(f"重构版要求 Elasticsearch 8.17.x，当前配置为 {self.es_version!r}")
        configured_ensure = configured_extra.get("ensure_index_on_init")
        if configured_ensure is not None:
            ensure_index = bool(configured_ensure)
        self._ensure_index_on_init = ensure_index
        self._impls: "OrderedDict[str, SimpleNamespace]" = OrderedDict()
        self._impl: Optional[SimpleNamespace] = None
        # Compatibility with the old implementation's per-process mapping cache.
        self.has_build_index: Dict[str, bool] = {}
        self._impl_for(self.index_name)

    # ------------------------------------------------------------------
    # Index routing and mapping
    # ------------------------------------------------------------------
    def _impl_for(self, index_name: str) -> SimpleNamespace:
        """创建并缓存一个 index 的兼容 binding，不再构造旧 ES7 实现。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        cached = self._impls.get(index)
        if cached is not None and self._ensure_index_on_init:
            try:
                exists = bool(cached.es.indices.exists(index=index))
            except Exception:
                # Keep a previously validated binding on an availability error;
                # the actual online search retains its per-route error fallback.
                logger.exception("ES8 cached index existence check failed: index=%s", index)
            else:
                if not exists:
                    self._impls.pop(index, None)
                    self.has_build_index.pop(index, None)
        if index not in self._impls:
            binding = SimpleNamespace(index_name=index, es=self.router.get_client_by_index(index))
            if self._ensure_index_on_init:
                self._ensure_index(index, binding=binding)
            self._impls[index] = binding
            if self._impl is None and index == self.index_name:
                self._impl = binding
        return self._impls[index]

    def _group_indexes(self, index_names: IndexNames) -> List[Tuple[SimpleNamespace, List[str]]]:
        """按 provider 分组索引，确保每组只使用对应连接池。"""
        names = _split_index_names(index_names, self.index_name)
        grouped: List[Tuple[str, List[str]]] = []
        for name in names:
            provider = self.router.resolve_provider(name)
            if not grouped or grouped[-1][0] != provider:
                grouped.append((provider, []))
            grouped[-1][1].append(name)
        result = []
        for _, group in grouped:
            for name in group:
                self._impl_for(name)
            result.append((self._impls[group[0]], group))
        return result

    def _get_index_name(self, index_names: IndexNames = None) -> str:
        """保留旧接口：规整索引名并确保每个目标索引经过 ES8 mapping 守卫。"""
        names = _split_index_names(index_names, self.index_name)
        for name in names:
            self._impl_for(name)
        return ",".join(names)

    def get_client_by_index(self, index_name: str) -> Any:
        """返回 index 对应的缓存 ES 8.17 client。"""
        return self.router.get_client_by_index(index_name)

    @property
    def es(self) -> Any:
        """兼容旧调用方，返回默认 index 对应的 ES 8.17 client。"""
        return self.get_client_by_index(self.index_name)

    def _vector_dimension(self) -> int:
        """返回主向量字段维度。"""
        return int(next(iter(self.vector_fields.values())))

    def _canonical_vector_field(self, vector_field: str) -> str:
        """将旧配置中的下划线字段名转换为 mapping 中的 dotted 字段名。"""
        if vector_field in {"indexes_embedding", "indexes.embedding"}:
            return "indexes.embedding"
        if vector_field in {"image_indexes_embedding", "image_indexes.embedding"}:
            return "image_indexes.embedding"
        return vector_field

    def _build_mapping(self) -> Dict[str, Any]:
        """构造 ES 8.17 mapping，主 nested dense_vector 开启 HNSW 索引。"""
        dims = self._vector_dimension()
        category_fields = (
            "category_path", "category_ids", "cate1_name", "cate1_id", "cate2_name",
            "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id",
        )
        return {
            "properties": {
                "title": {"type": "text", "analyzer": "ik_max_word"},
                "synonyms_title": {
                    "type": "text", "analyzer": "ik_max_word",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "content": {"type": "text", "analyzer": "ik_max_word"},
                "title_embedding": {
                    "type": "dense_vector", "dims": dims, "index": True,
                    "similarity": "cosine", "index_options": {"type": "hnsw"},
                },
                "content_embedding": {
                    "type": "dense_vector", "dims": dims, "index": True,
                    "similarity": "cosine", "index_options": {"type": "hnsw"},
                },
                "data_type": {"type": "keyword"}, "platform": {"type": "keyword"},
                "dataset": {"type": "keyword", "index": False}, "audit_result": {"type": "integer"},
                "del_flag": {"type": "integer"},
                "quality_level": {"type": "keyword", "normalizer": "lowercase"},
                "keywords": {"type": "keyword"}, "tags": {"type": "keyword"},
                "indexes": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "text", "analyzer": "ik_max_word"},
                        "embedding": {
                            "type": "dense_vector", "dims": dims, "index": True,
                            "similarity": "cosine", "index_options": {"type": "hnsw"},
                        },
                    },
                },
                "image_indexes": {
                    "type": "nested",
                    "properties": {
                        "text": {"type": "text", "index": True},
                        "embedding": {
                            "type": "dense_vector", "dims": dims, "index": True,
                            "similarity": "cosine", "index_options": {"type": "hnsw"},
                        },
                    },
                },
                "insert_time": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                "update_time": {"type": "date", "format": "yyyy-MM-dd HH:mm:ss"},
                "from_type": {"type": "keyword"}, "from_type_norm": {"type": "keyword"},
                "categorys_info": {"type": "object", "enabled": False},
                "task_id": {"type": "keyword", "index": True},
                "primary_category": {
                    "type": "object",
                    "properties": {field: {"type": "keyword"} for field in category_fields},
                },
                "multimodal_contents": {"type": "object", "enabled": False},
                "ext_info": {"type": "object"},
            }
        }

    @staticmethod
    def _existing_vector_mapping(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
        """从 get_mapping response 中取主向量字段 mapping。"""
        properties = mapping.get("mappings", {}).get("properties", {})
        return properties.get("indexes", {}).get("properties", {}).get("embedding", {})

    def _ensure_index(self, index_name: str, binding: Optional[SimpleNamespace] = None) -> None:
        """创建 native KNN 索引或拒绝不兼容的旧 ES7 mapping。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        binding = binding or self._impls.get(index)
        if binding is None:
            provider_client = self.router.get_client_by_index(index)
            binding = SimpleNamespace(index_name=index, es=provider_client)
        client = binding.es
        if index in self.has_build_index:
            return
        if not bool(client.indices.exists(index=index)):
            try:
                client.indices.create(
                    index=index,
                    settings={"number_of_shards": 3, "number_of_replicas": 1, "refresh_interval": "30s"},
                    mappings=self._build_mapping(),
                )
            except Exception as exc:
                # Workers may observe the same missing index. Only accept a
                # concurrent creator after validating its actual vector mapping.
                body = getattr(exc, "body", None)
                error = body.get("error") if isinstance(body, Mapping) else None
                if not isinstance(error, Mapping) or error.get("type") != "resource_already_exists_exception":
                    raise
            else:
                self.has_build_index[index] = True
                return
        mappings = _as_dict(client.indices.get_mapping(index=index))
        current = mappings.get(index) or (next(iter(mappings.values())) if mappings else {})
        properties = current.get("mappings", {}).get("properties", {})
        invalid_parent = [
            field for field in ("indexes", "image_indexes")
            if properties.get(field, {}).get("type") != "nested"
        ]
        vector_mappings = {
            "title_embedding": properties.get("title_embedding", {}),
            "content_embedding": properties.get("content_embedding", {}),
            "indexes.embedding": properties.get("indexes", {}).get("properties", {}).get("embedding", {}),
            "image_indexes.embedding": properties.get("image_indexes", {}).get("properties", {}).get("embedding", {}),
        }
        invalid = [
            field for field, vector_mapping in vector_mappings.items()
            if (
                vector_mapping.get("type") != "dense_vector"
                or vector_mapping.get("index") is not True
                or int(vector_mapping.get("dims", -1)) != self._vector_dimension()
                or vector_mapping.get("similarity") != "cosine"
                or vector_mapping.get("index_options", {}).get("type") != "hnsw"
            )
        ]
        invalid.extend(invalid_parent)
        if invalid:
            raise RuntimeError(
                f"索引 {index!r} 不是 ES8 native KNN mapping："
                f"向量字段 {', '.join(invalid)} 必须是 index=true、dims={self._vector_dimension()}、"
                "similarity=cosine、index_options.type=hnsw。"
                "旧 ES7/script_score 索引不能原地升级，请新建 ES8 索引并 reindex。"
            )
        self.has_build_index[index] = True

    def update_index_map(self, index_name: str, new_mapping: Dict[str, Any]) -> bool:
        """按 ES8 `put_mapping` 更新可新增的字段；向量 mapping 由 `_ensure_index` 守卫。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        properties = new_mapping.get("properties", new_mapping)
        try:
            response = self.get_client_by_index(index).indices.put_mapping(
                index=index, properties=properties
            )
            return bool(_response_value(response, "acknowledged", True))
        except Exception:
            logger.exception("ES8 mapping update failed: index=%s", index)
            return False

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------
    @staticmethod
    def _map_attribute_field(field: str) -> str:
        """复刻旧属性字段别名到 keyword 字段的映射。"""
        if field == "from_file_name":
            return "ext_info.from_file_name.keyword"
        return f"primary_category.{field}" if field in _CATEGORY_FIELDS else field

    @classmethod
    def _attribute_clauses(cls, attributes: Any) -> Tuple[List[Dict[str, Any]], bool]:
        """生成属性过滤子句，并返回是否显式提供 del_flag。"""
        if not attributes:
            return [], False
        explicit_del_flag = False

        def one_group(group: Mapping[str, Any]) -> List[Dict[str, Any]]:
            nonlocal explicit_del_flag
            clauses: List[Dict[str, Any]] = []
            for raw_field, value in group.items():
                field = cls._map_attribute_field(str(raw_field))
                if field == "del_flag":
                    explicit_del_flag = True
                if field == "_id":
                    values = list(value) if isinstance(value, (list, tuple, set)) else [value]
                    clauses.append({"ids": {"values": values}})
                    continue
                if isinstance(value, (list, tuple, set)) or field == "keywords":
                    values = list(value) if isinstance(value, (list, tuple, set)) else [value]
                    clauses.append({"terms": {field: values}})
                else:
                    clauses.append({"term": {field: value}})
            return clauses

        if isinstance(attributes, list):
            groups = []
            for group in attributes:
                if isinstance(group, Mapping):
                    clauses = one_group(group)
                    if clauses:
                        groups.append({"bool": {"must": clauses}})
            return ([{"bool": {"should": groups, "minimum_should_match": 1}}] if groups else []), explicit_del_flag
        if isinstance(attributes, Mapping):
            return one_group(attributes), explicit_del_flag
        raise ValueError("attribute 必须是 dict 或 list[dict]")

    @classmethod
    def _filter_clauses(cls, query: Mapping[str, Any], include_default_del_flag: bool = True) -> List[Dict[str, Any]]:
        """构造时间、属性和默认软删除过滤条件。"""
        clauses: List[Dict[str, Any]] = []
        for time_field in ("insert_time", "update_time"):
            time_range = query.get(time_field)
            if isinstance(time_range, (list, tuple)) and len(time_range) == 2:
                condition = {}
                if time_range[0]:
                    condition["gte"] = time_range[0]
                if time_range[1]:
                    condition["lte"] = time_range[1]
                if condition:
                    clauses.append({"range": {time_field: condition}})
        attribute_clauses, explicit_del_flag = cls._attribute_clauses(query.get("attribute"))
        clauses.extend(attribute_clauses)
        if include_default_del_flag and not explicit_del_flag:
            clauses.append({"term": {"del_flag": 0}})
        return clauses

    @classmethod
    def _filter_query(cls, query: Mapping[str, Any], include_default_del_flag: bool = True) -> Dict[str, Any]:
        """返回可作为 bool.must 使用的 filter query。"""
        clauses = cls._filter_clauses(query, include_default_del_flag=include_default_del_flag)
        return {"bool": {"must": clauses}} if clauses else {"match_all": {}}

    @staticmethod
    def _text_clauses(query: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """构造 BM25 文本 should 子句。"""
        values = query.get("query")
        values = values if isinstance(values, list) else [values]
        clauses: List[Dict[str, Any]] = []
        for text in values:
            if not text:
                continue
            clauses.extend([
                {"multi_match": {"query": text, "fields": ["title^2", "content^1.5", "indexes.text"], "type": "best_fields", "tie_breaker": 0.3}},
                {"match": {"synonyms_title": {"query": text, "boost": 1.8}}},
            ])
        return clauses

    @staticmethod
    def _fields_query(query: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """支持旧 search 接口的 fields match 结构。"""
        fields = query.get("fields")
        if not isinstance(fields, Mapping):
            return None
        return {"bool": {"must": [{"match": {field: value}} for field, value in fields.items()]}}

    def _validate_vector(self, vector: Sequence[float]) -> None:
        """校验 query vector 维度。"""
        if vector is None or len(vector) != self._vector_dimension():
            raise ValueError(f"向量维度必须为 {self._vector_dimension()}")

    def _validate_query_vectors(self, query: Mapping[str, Any]) -> None:
        """校验 query 中所有向量，即使调用方选择了 BM25-only 分页路径。"""
        values = query.get("vector")
        if not values:
            return
        values = values if isinstance(values, list) else [values]
        for item in values:
            vector = item.get("value") if isinstance(item, Mapping) else item
            self._validate_vector(vector)

    def _build_knn_clause(
        self,
        query_vector: Sequence[float],
        vector_field: str = "indexes.embedding",
        k: int = 10,
        num_candidates: Optional[int] = None,
        filter_query: Optional[Dict[str, Any]] = None,
        with_inner_hits: bool = False,
    ) -> Dict[str, Any]:
        """构造 ES8 nested KNN query，不再使用 script_score。"""
        field = self._canonical_vector_field(vector_field)
        k = max(1, int(k))
        candidates = max(k, int(num_candidates or max(100, k * 10)))
        knn = {
            "field": field,
            "query_vector": [float(value) for value in query_vector],
            "k": k,
            "num_candidates": candidates,
        }
        if filter_query:
            knn["filter"] = filter_query
        if "." in field and field.split(".", 1)[0] in {"indexes", "image_indexes"}:
            nested: Dict[str, Any] = {
                "path": field.split(".", 1)[0],
                "score_mode": "max",
                "query": {"knn": knn},
            }
            if with_inner_hits:
                # Alibaba's ES 8.17 parser accepts inner_hits on the nested
                # query, but rejects it inside the nested knn clause with
                # ``[knn] unknown field [inner_hits]``.  Nested inner hits
                # return a relative source, but request filtering uses full
                # field paths, as in the old ES7 engine.
                nested["inner_hits"] = {
                    "name": "best_index",
                    "size": 3,
                    "_source": {"includes": [nested["path"] + ".text", nested["path"] + ".embedding"]},
                }
            return {"nested": nested}
        return {"knn": knn}

    def _build_search_query(
        self,
        query: Mapping[str, Any],
        include_text: bool = True,
        include_vector: bool = True,
        vector_k: int = 10,
        with_inner_hits: bool = False,
    ) -> Dict[str, Any]:
        """构造 ES8 search(query=...) 参数中的 bool DSL。"""
        should: List[Dict[str, Any]] = []
        filter_query = self._filter_query(query)
        if include_text:
            should.extend(self._text_clauses(query))
            fields_query = self._fields_query(query)
            if fields_query:
                should.append(fields_query)
        if include_vector and query.get("vector"):
            values = query["vector"] if isinstance(query["vector"], list) else [query["vector"]]
            for item in values:
                vector = item.get("value") if isinstance(item, Mapping) else item
                self._validate_vector(vector)
                should.append(self._build_knn_clause(
                    vector, k=vector_k, filter_query=filter_query,
                    with_inner_hits=with_inner_hits,
                ))
        body: Dict[str, Any] = {"must": [filter_query]}
        if should:
            body["should"] = should
            body["minimum_should_match"] = 1
        return {"bool": body}

    # ------------------------------------------------------------------
    # ES8 request/response helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _total(response: Mapping[str, Any]) -> int:
        """解析 hits.total 的 ES8 object/int 两种形式。"""
        value = response.get("hits", {}).get("total", 0)
        return int(value.get("value", 0) if isinstance(value, Mapping) else value or 0)

    @staticmethod
    def _hits(response: Mapping[str, Any], include_index: bool = False) -> List[Dict[str, Any]]:
        """把 ES hit 转成旧上层使用的文档结构。"""
        docs = []
        for hit in response.get("hits", {}).get("hits", []) or []:
            doc = {"_id": hit.get("_id"), "score": hit.get("_score", 0)}
            if include_index:
                doc["_index"] = hit.get("_index")
            doc.update(hit.get("_source") or {})
            docs.append(doc)
        return docs

    def _search_request(
        self,
        client: Any,
        indexes: Sequence[str],
        query: Dict[str, Any],
        size: int,
        from_: int = 0,
        min_score: Optional[float] = None,
        sort: Optional[Sequence[Any]] = None,
        search_after: Optional[Sequence[Any]] = None,
        scroll: Optional[str] = None,
        source_includes: Optional[Sequence[str]] = None,
        source_excludes: Optional[Sequence[str]] = None,
        aggs: Optional[Dict[str, Any]] = None,
        track_total_hits: Optional[Union[bool, int]] = None,
        source: Optional[Union[bool, Mapping[str, Any]]] = None,
        pit: Optional[Mapping[str, Any]] = None,
        seq_no_primary_term: bool = False,
        stored_fields: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """使用 ES8 named parameters 发起 search 请求。"""
        kwargs: Dict[str, Any] = {"query": query, "size": int(size)}
        if pit is None:
            kwargs["index"] = ",".join(indexes)
        else:
            kwargs["pit"] = dict(pit)
        if from_:
            kwargs["from_"] = int(from_)
        if min_score is not None:
            kwargs["min_score"] = min_score
        if sort is not None:
            kwargs["sort"] = sort
        if search_after is not None:
            kwargs["search_after"] = search_after
        if scroll is not None:
            kwargs["scroll"] = scroll
        if source_includes:
            kwargs["source_includes"] = list(source_includes)
        if source_excludes:
            kwargs["source_excludes"] = list(source_excludes)
        if aggs is not None:
            kwargs["aggs"] = aggs
        if track_total_hits is not None:
            kwargs["track_total_hits"] = track_total_hits
        if source is not None:
            kwargs["source"] = source
        if seq_no_primary_term:
            kwargs["seq_no_primary_term"] = True
        if stored_fields is not None:
            kwargs["stored_fields"] = list(stored_fields)
        last_response: Dict[str, Any] = {}
        for attempt in range(_SHARD_RETRY_TIMES):
            response = _as_dict(client.search(**kwargs))
            last_response = response
            if pit is not None and response.get("pit_id"):
                kwargs["pit"] = {**kwargs["pit"], "id": response["pit_id"]}
                if isinstance(pit, dict):
                    pit["id"] = response["pit_id"]
            shards = response.get("_shards") or {}
            if not response.get("timed_out") and not shards.get("failed"):
                return response
            if attempt + 1 < _SHARD_RETRY_TIMES:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(
            f"分片查询失败，已重试 {_SHARD_RETRY_TIMES} 次: "
            f"index={kwargs.get('index')}, shards={last_response.get('_shards')}"
        )

    def _search_with_shard_check(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """Run a legacy body-shaped search through ES8 named parameters."""
        source = body.get("_source") or {}
        source_includes = source.get("includes") if isinstance(source, Mapping) else None
        source_excludes = source.get("excludes") if isinstance(source, Mapping) else None
        client = self.get_client_by_index(search_index)
        kwargs: Dict[str, Any] = {
            "index": str(search_index),
            "query": body.get("query") or {"match_all": {}},
            "size": int(body.get("size", 10)),
        }
        if body.get("from"):
            kwargs["from_"] = int(body["from"])
        if body.get("sort") is not None:
            kwargs["sort"] = body["sort"]
        if body.get("min_score") is not None:
            kwargs["min_score"] = body["min_score"]
        if source_includes:
            kwargs["source_includes"] = source_includes
        if source_excludes:
            kwargs["source_excludes"] = source_excludes
        if body.get("aggs") is not None:
            kwargs["aggs"] = body["aggs"]
        return self._search_request(
            client, [str(search_index)], kwargs["query"], kwargs["size"],
            from_=kwargs.get("from_", 0), min_score=kwargs.get("min_score"),
            sort=kwargs.get("sort"), source_includes=kwargs.get("source_includes"),
            source_excludes=kwargs.get("source_excludes"), aggs=kwargs.get("aggs"),
        )

    @staticmethod
    def _assign_dotted(payload: Dict[str, Any], field: str, value: Any) -> None:
        """把 dotted 字段写成真正的 nested JSON，而不是 literal dotted key。"""
        parts = [part for part in str(field).split(".") if part]
        if len(parts) == 1:
            payload[parts[0]] = value
            return
        cursor: Dict[str, Any] = payload
        for part in parts[:-1]:
            existing = cursor.get(part)
            if not isinstance(existing, dict):
                existing = {}
                cursor[part] = existing
            cursor = existing
        cursor[parts[-1]] = value

    @staticmethod
    def _painless_assignment(field: str, param: str) -> str:
        parts = [part for part in str(field).split(".") if part]
        if len(parts) == 1:
            return f"ctx._source['{parts[0]}'] = params.{param}"
        path = "ctx._source" + "".join(f"['{part}']" for part in parts)
        return f"{path} = params.{param}"

    def _single_search_with_retry(self, index_str: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """旧 body 入口的 ES8 named-parameter 兼容包装。"""
        return self._search_with_shard_check(index_str, body)

    def _search_once_with_retry(self, search_index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """保留旧方法名，分片失败时由 `_search_request` 统一重试。"""
        return self._search_with_shard_check(search_index, body)

    def _native_msearch_with_retry(self, client: Any, searches: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量执行线上召回；成功子请求不重跑，耗尽后保留可用部分命中。"""
        if len(searches) % 2:
            raise ValueError("msearch requires alternating headers and bodies")
        if not searches:
            return {"responses": []}
        responses: List[Dict[str, Any]] = [{} for _ in range(len(searches) // 2)]
        pending = list(range(len(responses)))
        for attempt in range(_SHARD_RETRY_TIMES):
            batch = [item for position in pending for item in searches[2 * position:2 * position + 2]]
            try:
                result = _as_dict(client.msearch(
                    searches=batch, max_concurrent_searches=_MSEARCH_MAX_CONCURRENT_SEARCHES,
                ))
                values = result.get("responses")
                if not isinstance(values, list) or len(values) != len(pending) or any(
                    not isinstance(value, Mapping) for value in values
                ):
                    raise RuntimeError("ES8 msearch response cardinality/shape mismatch")
            except Exception:
                if attempt == 0:
                    raise
                logger.exception("ES8 msearch retry failed; retaining previous partial responses")
                break
            retry = []
            for position, value in zip(pending, values):
                responses[position] = dict(value)
                if not value.get("error") and (
                    value.get("timed_out") or (value.get("_shards") or {}).get("failed")
                ):
                    retry.append(position)
            pending = retry
            if not pending:
                break
            if attempt + 1 < _SHARD_RETRY_TIMES:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        for position in pending:
            logger.warning(
                "ES8 msearch partial recall retained after retries: index=%s shards=%s timed_out=%s",
                searches[2 * position].get("index"), responses[position].get("_shards"),
                responses[position].get("timed_out"),
            )
        return {"responses": responses}

    def _msearch_with_shard_check(self, msearch_body: List[Dict[str, Any]]) -> Dict[str, Any]:
        """保留旧 body 接口，按连续 provider 原生批量执行并保持响应位置。"""
        if len(msearch_body) % 2:
            raise ValueError("msearch requires alternating headers and bodies")
        groups: List[Tuple[str, Any, List[Dict[str, Any]]]] = []
        for position in range(0, len(msearch_body), 2):
            header, body = msearch_body[position:position + 2]
            if not isinstance(header, Mapping) or not isinstance(body, Mapping):
                raise ValueError("msearch headers and bodies must be mappings")
            names = _split_index_names(header.get("index"), self.index_name)
            providers = {self.router.resolve_provider(name) for name in names}
            if len(providers) != 1:
                raise ValueError("one msearch header cannot span different providers")
            provider = providers.pop()
            bindings = [self._impl_for(name) for name in names]
            if not groups or groups[-1][0] != provider:
                groups.append((provider, bindings[0].es, []))
            groups[-1][2].extend([{**header, "index": ",".join(names)}, dict(body)])
        responses = []
        for _, client, searches in groups:
            responses.extend(self._native_msearch_with_retry(client, searches)["responses"])
        return {"responses": responses}

    def _scroll_request(self, client: Any, scroll_id: str, scroll_timeout: str) -> Dict[str, Any]:
        """继续 scroll 并对 ES8 返回的部分分片失败做同样的重试。"""
        last_response: Dict[str, Any] = {}
        for attempt in range(_SHARD_RETRY_TIMES):
            last_response = _as_dict(
                client.scroll(scroll_id=scroll_id, scroll=scroll_timeout)
            )
            shards = last_response.get("_shards") or {}
            if not last_response.get("timed_out") and not shards.get("failed"):
                return last_response
            if attempt + 1 < _SHARD_RETRY_TIMES:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(f"scroll 分片查询失败，已重试 {_SHARD_RETRY_TIMES} 次")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def insert(self, data: Dict[str, Any], index_names: IndexNames = None, refresh_imm: bool = False) -> bool:
        """用 ES8 update(doc_as_upsert) 写入一条已含向量的文档。"""
        if "_id" not in data:
            logger.error("数据必须包含_id字段")
            return False
        payload = copy.deepcopy(data)
        doc_id = str(payload.pop("_id"))
        if "indexes" in payload:
            if not isinstance(payload["indexes"], list):
                return False
            valid_indexes = []
            for item in payload["indexes"]:
                if not isinstance(item, dict) or "embedding" not in item or "text" not in item:
                    return False
                try:
                    self._validate_vector(item["embedding"])
                except ValueError:
                    return False
                if not all(value == 0 for value in item["embedding"]):
                    valid_indexes.append(item)
            if valid_indexes:
                payload["indexes"] = valid_indexes
            else:
                payload.pop("indexes", None)
        ok = True
        for binding, names in self._group_indexes(index_names):
            for index in names:
                response = binding.es.update(index=index, id=doc_id, doc=payload, doc_as_upsert=True, refresh=refresh_imm)
                ok = ok and _response_value(response, "result") in {"created", "updated", "noop"}
                if refresh_imm:
                    binding.es.indices.refresh(index=index)
        return ok

    def update(self, data_id: str, data: Dict[str, Any], index_names: IndexNames = None) -> bool:
        """用 ES8 update(doc=...) 局部更新文档。"""
        update_doc: Dict[str, Any] = {}
        for field, value in (data or {}).items():
            self._assign_dotted(update_doc, field, copy.deepcopy(value))
        ok = True
        for binding, names in self._group_indexes(index_names):
            for index in names:
                response = binding.es.update(index=index, id=str(data_id), doc=update_doc)
                ok = ok and _response_value(response, "result") in {"updated", "noop"}
        return ok

    def delete(self, data_id: str, index_names: IndexNames = None, refresh: bool = False) -> bool:
        """用 ES8 delete API 删除文档。"""
        ok = True
        for binding, names in self._group_indexes(index_names):
            for index in names:
                response = binding.es.delete(index=index, id=str(data_id), refresh=refresh)
                ok = ok and _response_value(response, "result") in {"deleted", "not_found"}
                if refresh:
                    binding.es.indices.refresh(index=index)
        return ok

    def get(self, data_id: str, index_names: IndexNames = None) -> Optional[Dict[str, Any]]:
        """用 ES8 get API 读取第一个命中的文档。"""
        for binding, names in self._group_indexes(index_names):
            for index in names:
                try:
                    response = _as_dict(binding.es.get(index=index, id=str(data_id)))
                except Exception:
                    continue
                if response.get("found", True) is False:
                    continue
                return {"_id": response.get("_id", data_id), **(response.get("_source") or {})}
        return None

    def insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]]) -> bool:
        """用 ES8 index(document=...) 写入带多个根向量的文档。"""
        payload = copy.deepcopy(data)
        if "_id" not in payload:
            return False
        for field, vector in vectors.items():
            if len(vector) != self._vector_dimension():
                return False
            self._assign_dotted(payload, self._canonical_vector_field(field), vector)
        doc_id = str(payload.pop("_id"))
        ok = True
        for binding, names in self._group_indexes(None):
            for index in names:
                response = binding.es.index(index=index, id=doc_id, document=payload)
                ok = ok and _response_value(response, "result") in {"created", "updated"}
        return ok

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def search(self, query: Optional[Dict[str, Any]] = None, size: int = 10, index_names: IndexNames = None) -> List[Dict[str, Any]]:
        """执行单路 BM25/native KNN 混合 query。"""
        query = query or {}
        results: List[Dict[str, Any]] = []
        for binding, names in self._group_indexes(index_names):
            response = self._search_request(binding.es, names, self._build_search_query(query), size=size)
            results.extend(self._hits(response))
        return results

    def _build_es_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """兼容旧调用方，返回 ES8 query DSL（不包含 body 包装）。"""
        if isinstance(query, Mapping) and isinstance(query.get("fields"), Mapping):
            return self._fields_query(query) or {"match_all": {}}
        return self._build_search_query(query or {})

    def _build_nested_vector_clause(
        self,
        vector_value: List[float],
        with_inner_hits: bool = False,
        boost: Optional[float] = None,
        score_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """旧方法名兼容层；返回 ES8 native nested KNN，不生成 script_score。"""
        del with_inner_hits, boost, score_mode
        self._validate_vector(vector_value)
        return self._build_knn_clause(vector_value, vector_field="indexes.embedding", k=10)

    @staticmethod
    def _restore_inner_embeddings(hit: Dict[str, Any], doc: Dict[str, Any]) -> None:
        """按 native nested KNN 的路径和offset回填文本/图片向量。"""
        for inner in (hit.get("inner_hits") or {}).values():
            for inner_hit in inner.get("hits", {}).get("hits", []) or []:
                nested = inner_hit.get("_nested") or {}
                path = nested.get("field", "indexes")
                if path not in {"indexes", "image_indexes"}:
                    continue
                items = doc.get(path)
                offset = nested.get("offset")
                embedding = (inner_hit.get("_source") or {}).get("embedding")
                if isinstance(items, list) and isinstance(offset, int) and embedding is not None and 0 <= offset < len(items):
                    if isinstance(items[offset], dict):
                        items[offset]["embedding"] = embedding

    @staticmethod
    def _merge_index_embeddings(target: Dict[str, Any], other: Dict[str, Any]) -> None:
        """按文本补齐 dual 两路返回中缺失的 nested 向量。"""
        for path in ("indexes", "image_indexes"):
            target_indexes = target.get(path)
            other_indexes = other.get(path)
            if not isinstance(target_indexes, list) or not isinstance(other_indexes, list):
                continue
            embeddings = {
                item.get("text"): item.get("embedding")
                for item in other_indexes
                if isinstance(item, dict) and item.get("text") and item.get("embedding") is not None
            }
            for item in target_indexes:
                if isinstance(item, dict) and not item.get("embedding"):
                    embedding = embeddings.get(item.get("text"))
                    if embedding is not None:
                        item["embedding"] = embedding

    def search_by_vector(
        self, query_vector: List[float], vector_field: str, size: int = 10, min_score: float = 0.0,
        return_score: bool = False, extra_query: Optional[Dict[str, Any]] = None,
        index_names: IndexNames = None,
    ) -> Any:
        """执行 ES8 native KNN 检索。"""
        self._validate_vector(query_vector)
        filter_query = self._filter_query(extra_query or {})
        knn = self._build_knn_clause(
            query_vector,
            vector_field=self._canonical_vector_field(vector_field),
            k=max(1, int(size)),
            filter_query=filter_query,
        )
        query_dsl = {"bool": {"must": [filter_query], "should": [knn], "minimum_should_match": 1}}
        output: List[Any] = []
        for binding, names in self._group_indexes(index_names):
            response = self._search_request(binding.es, names, query_dsl, size=size, min_score=min_score)
            for doc in self._hits(response):
                score = doc.pop("score", 0)
                output.append((doc, score) if return_score else doc)
        return output

    def _search_multi_group(self, binding: SimpleNamespace, names: List[str], query: Dict[str, Any], size: int, mode: str) -> Tuple[List[Dict[str, Any]], int]:
        """在一个 provider 内执行 dual 两路并按文档 id 合并。"""
        has_text = bool(self._text_clauses(query) or self._fields_query(query))
        has_vector = bool(query.get("vector"))
        dual = mode == "dual" and has_text and has_vector
        lean_source = mode == "dual" and has_vector
        if dual:
            routes = [("bm25", True, False, max(1, size // 2)), ("vector", False, True, max(1, size // 2))]
        elif mode == "bm25":
            routes = [("bm25", True, False, size)]
        elif mode == "vector":
            routes = [("vector", False, True, size)]
        else:
            routes = [("single", has_text, has_vector, size)]
        merged: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        route_totals: Dict[str, int] = {route_name or "single": 0 for route_name, *_ in routes}
        plan = []
        searches = []
        for one_index in names:
            for route_name, include_text, include_vector, route_size in routes:
                route_query = self._build_search_query(
                    query,
                    include_text=include_text,
                    include_vector=include_vector,
                    vector_k=max(1, route_size),
                    with_inner_hits=include_vector,
                )
                # Separate subsearches retain each index's original budget while
                # one native msearch executes routes with bounded concurrency.
                plan.append((one_index, route_name, route_query, route_size))
                route_body = {"query": route_query, "size": route_size}
                if lean_source:
                    route_body["_source"] = {"excludes": list(_LEAN_SOURCE_EXCLUDES)}
                searches.extend([{"index": one_index}, route_body])
        responses = None
        if len(plan) > 1:
            try:
                responses = self._native_msearch_with_retry(binding.es, searches)["responses"]
            except Exception:
                logger.exception("ES8 native msearch failed: indexes=%s; falling back to independent searches", names)
        if responses is None:
            responses = []
            for one_index, route_name, route_query, route_size in plan:
                try:
                    response = self._search_request(
                        binding.es, [one_index], route_query, size=route_size,
                        source_excludes=_LEAN_SOURCE_EXCLUDES if lean_source else None,
                    )
                except Exception:
                    logger.exception("ES8 native recall route failed: route=%s index=%s", route_name, one_index)
                    response = {"error": {"type": "independent_search_failed"}}
                responses.append(response)
        for (one_index, route_name, _, _), response in zip(plan, responses):
            if response.get("error"):
                logger.warning("ES8 native recall route failed: route=%s index=%s error=%s", route_name, one_index, response["error"])
                continue
            route_totals[route_name or "single"] += self._total(response)
            for hit in response.get("hits", {}).get("hits", []) or []:
                key = f"{hit.get('_index', one_index)}:{hit.get('_id')}"
                if key not in merged:
                    doc = {
                        "_index": hit.get("_index", one_index),
                        "_id": hit.get("_id"),
                        "score": hit.get("_score", 0),
                    }
                    doc.update(hit.get("_source") or {})
                    self._restore_inner_embeddings(hit, doc)
                    merged[key] = doc
                else:
                    other = {**(hit.get("_source") or {})}
                    self._restore_inner_embeddings(hit, other)
                    self._merge_index_embeddings(merged[key], other)
                    for field, value in (hit.get("_source") or {}).items():
                        merged[key].setdefault(field, value)
            logger.debug("native recall route=%s index=%s hits=%d", route_name, one_index, len(response.get("hits", {}).get("hits", []) or []))
        total = max(route_totals.values()) if dual else next(iter(route_totals.values()), 0)
        return list(merged.values()), total

    def search_multi(self, query: Dict[str, Any], index_names: IndexNames = None, size: int = 10, page_num: int = 1, recall_mode: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """执行 BM25/vector 分路召回并合并，vector 路使用 native KNN。"""
        del page_num
        query = query or {}
        mode = str(recall_mode or self.recall_mode).lower()
        if mode == "legacy":
            mode = "single"
        if mode not in {"dual", "single", "bm25", "vector"}:
            raise ValueError(f"不支持的 recall_mode: {mode}")
        docs: List[Dict[str, Any]] = []
        total = 0
        for binding, names in self._group_indexes(index_names):
            group_docs, group_total = self._search_multi_group(binding, names, query, size, mode)
            docs.extend(group_docs)
            total += group_total
        return docs, total

    def search_multi_by_page(self, query: Dict[str, Any], index_names: IndexNames = None, size: int = 10, page_num: int = 1, score_threshold: Optional[float] = None) -> Tuple[List[Dict[str, Any]], int]:
        """执行 BM25 分页检索；分页接口不把 native KNN 混入 from/size。"""
        query = query or {}
        try:
            self._validate_query_vectors(query)
        except ValueError:
            logger.exception("ES8 分页查询向量维度错误")
            return [], 0
        docs: List[Dict[str, Any]] = []
        total = 0
        remaining_offset = max(0, (page_num - 1) * size)
        for binding, names in self._group_indexes(index_names):
            for name in names:
                response = self._search_request(
                    binding.es, [name], self._build_search_query(query, include_text=True, include_vector=False),
                    size=size, from_=remaining_offset,
                    min_score=(score_threshold if (score_threshold is not None and (query.get("query") or query.get("vector"))) else None),
                    source_excludes=_VECTOR_SOURCE_EXCLUDES,
                )
                index_total = self._total(response)
                docs.extend(self._hits(response))
                total += index_total
                # Preserve the old multi-index global pagination contract: the
                # offset is consumed by earlier indexes before later indexes.
                remaining_offset = max(0, remaining_offset - index_total)
        if len(docs) > size:
            docs = docs[:size]
        return docs, total

    def scroll_search(self, query: Dict[str, Any], batch_size: int = 1000, scroll_timeout: str = "5m", index_names: IndexNames = None) -> Iterator[Dict[str, Any]]:
        """使用 ES8 named scroll/clear_scroll API 迭代 BM25 结果。"""
        query = query or {}

        def iterate() -> Iterator[Dict[str, Any]]:
            for binding, names in self._group_indexes(index_names):
                response = self._search_request(binding.es, names, self._build_search_query(query, include_vector=False), size=batch_size, scroll=scroll_timeout)
                scroll_id = response.get("_scroll_id")
                try:
                    while True:
                        hits = response.get("hits", {}).get("hits", []) or []
                        if not hits:
                            break
                        yield from self._hits(response)
                        if not scroll_id:
                            break
                        response = self._scroll_request(binding.es, scroll_id, scroll_timeout)
                        scroll_id = response.get("_scroll_id", scroll_id)
                finally:
                    if scroll_id:
                        binding.es.clear_scroll(scroll_id=scroll_id)

        return iterate()

    def search_after(self, query: Dict[str, Any], batch_size: int = 1000, sort_field: str = "_id", index_names: IndexNames = None) -> Iterator[Dict[str, Any]]:
        """使用 ES8 search_after 参数迭代 BM25 结果。"""
        query = query or {}

        def iterate() -> Iterator[Dict[str, Any]]:
            for binding, names in self._group_indexes(index_names):
                after = None
                while True:
                    response = self._search_request(binding.es, names, self._build_search_query(query, include_vector=False), size=batch_size, sort=[{sort_field: "asc"}], search_after=after)
                    hits = response.get("hits", {}).get("hits", []) or []
                    if not hits:
                        break
                        yield from self._hits(response)
                    after = hits[-1].get("sort")
                    if not after:
                        break

        return iterate()

    # ------------------------------------------------------------------
    # Aggregations and updates
    # ------------------------------------------------------------------
    def get_unique_values(self, index_name: str, field_name: str, size: int = 10000, include_doc_count: bool = False, extra_query: Optional[Dict[str, Any]] = None) -> Union[List[str], List[Dict[str, Any]]]:
        """用 ES8 search(query=, aggs=) 执行 terms 聚合。"""
        values: List[Any] = []
        seen = set()
        for binding, names in self._group_indexes(index_name):
            response = self._search_request(
                binding.es, names, self._filter_query(extra_query or {}), size=0,
                aggs={"unique_vals": {"terms": {"field": field_name, "size": size}}},
            )
            for bucket in response.get("aggregations", {}).get("unique_vals", {}).get("buckets", []) or []:
                key = bucket.get("key")
                if key in seen:
                    continue
                seen.add(key)
                values.append({"value": key, "doc_count": bucket.get("doc_count", 0)} if include_doc_count else key)
        return values

    def get_field_statistics(self, index_name: str, field_name: str, extra_query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """汇总 terms 聚合统计。"""
        values = self.get_unique_values(index_name, field_name, include_doc_count=True, extra_query=extra_query)
        sorted_values = sorted(values, key=lambda item: item["doc_count"], reverse=True)
        return {"field_name": field_name, "unique_count": len(sorted_values), "total_docs": sum(item["doc_count"] for item in sorted_values), "top_values": sorted_values[:10], "all_values": sorted_values}

    def update_value(self, index_name: IndexNames, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]) -> bool:
        """按原条件更新；Serverless使用无脚本且有版本保护的写入。"""
        if not update_value_dict:
            return True
        # 旧 update_value 的 conditions 是 AND 关系；search_multi 的 attribute list
        # 才是 OR 关系，不能直接复用同一个 list 解析入口。
        condition_clauses: List[Dict[str, Any]] = []
        for condition in conditions or []:
            clauses, _ = self._attribute_clauses(condition)
            condition_clauses.extend(clauses)
        query = {"bool": {"must": condition_clauses}} if condition_clauses else {"match_all": {}}
        groups = self._group_indexes(index_name)
        try:
            for binding, names in groups:
                for response in self._conditional_update_responses(
                    binding, names, query, update_value_dict, 500, "abort",
                ):
                    if response.get("failures") or response.get("version_conflicts"):
                        logger.error("ES8 update_value incomplete: indexes=%s", names)
                        return False
        except Exception:
            logger.exception("ES8 update_value failed: index=%s", index_name)
            return False
        return True


    @staticmethod
    def _checked_update_response(response: Any) -> Dict[str, Any]:
        """A successful HTTP envelope is not proof of a successful update."""
        result = _as_dict(response)
        if result.get("error"):
            error = result["error"]
            kind = error.get("type", "unknown") if isinstance(error, Mapping) else "unknown"
            raise RuntimeError(f"ES8 conditional update failed: {kind}")
        if "completed" in result or "task" in result:
            if result.get("completed") is not True or not isinstance(result.get("response"), Mapping):
                raise RuntimeError("ES8 conditional update task has no completed result")
            result = dict(result["response"])
        if result.get("error") or result.get("timed_out"):
            raise RuntimeError("ES8 conditional update failed or timed out")
        for key in ("updated", "total", "version_conflicts"):
            value = result.get(key, 0 if key == "version_conflicts" else None)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise RuntimeError("ES8 conditional update statistics are incomplete")
        if not isinstance(result.get("failures", []), list):
            raise RuntimeError("ES8 conditional update failures are malformed")
        return result


    @staticmethod
    def _apply_source_assignments(source: Mapping[str, Any], update_fields: Mapping[str, Any]) -> Dict[str, Any]:
        """Apply the old assignment semantics without merging/replacing parents."""
        document = copy.deepcopy(dict(source))
        for field, value in update_fields.items():
            if not isinstance(field, str) or not field or any(not part for part in field.split(".")):
                raise ValueError("条件更新字段路径无效")
            parts = field.split(".")
            parent = document
            for part in parts[:-1]:
                if not isinstance(parent.get(part), dict):
                    raise ValueError("条件更新dotted路径的父字段不存在或不是对象")
                parent = parent[part]
            parent[parts[-1]] = copy.deepcopy(value)
        return document


    def _update_without_script(
        self, client: Any, indexes: Sequence[str], query: Dict[str, Any],
        update_fields: Dict[str, Any], requests_per_second: int, conflicts: str,
    ) -> Dict[str, Any]:
        """Snapshot + full-source CAS preserves script assignment semantics."""
        from elasticsearch.serializer import JSONSerializer

        if conflicts not in {"abort", "proceed"}:
            raise ValueError("unknown conflicts policy")
        if not isinstance(requests_per_second, numbers.Real) or not math.isfinite(requests_per_second):
            raise ValueError("requests_per_second must be finite")
        result = {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}
        pit = {"keep_alive": "5m"}
        after = None
        expected_total = None
        serializer = JSONSerializer()
        opened = _as_dict(client.open_point_in_time(
            index=",".join(indexes), keep_alive="5m", allow_partial_search_results=False,
        ))
        pit["id"] = opened.get("id")
        if not pit["id"]:
            raise RuntimeError("条件更新未能打开完整PIT")
        try:
            while True:
                started = time.monotonic()
                page_size = min(50, max(1, int(requests_per_second * 30))) if requests_per_second > 0 else 50
                maintenance_options = getattr(self, "_maintenance_update_options", None)
                if maintenance_options:
                    page_size = min(page_size, maintenance_options["scroll_size"])
                response = self._search_request(
                    client, indexes, query, page_size, sort=[{"_shard_doc": "asc"}],
                    pit=pit, search_after=after, source=True, track_total_hits=True,
                    seq_no_primary_term=True, stored_fields=["_routing"],
                )
                if response.get("error"):
                    raise RuntimeError("条件更新读取失败，不能确认完整快照")
                total = response.get("hits", {}).get("total")
                if expected_total is None:
                    if isinstance(total, int):
                        expected_total = total
                    elif isinstance(total, Mapping) and total.get("relation", "eq") == "eq":
                        expected_total = total.get("value")
                    if isinstance(expected_total, bool) or not isinstance(expected_total, int) or expected_total < 0:
                        raise RuntimeError("条件更新缺少精确snapshot total")
                hits = response.get("hits", {}).get("hits", []) or []
                if not hits:
                    if result["total"] != expected_total:
                        raise RuntimeError("条件更新快照提前结束，已成功部分不会回滚")
                    break
                next_after = hits[-1].get("sort")
                if not next_after or next_after == after:
                    raise RuntimeError("条件更新缺少有效PIT cursor")
                if result["total"] + len(hits) > expected_total:
                    raise RuntimeError("条件更新快照返回重复或额外记录")
                chunks: List[List[Any]] = []
                operations: List[Any] = []
                byte_count = 0
                for hit in hits:
                    if (not isinstance(hit.get("_source"), Mapping)
                            or any(hit.get(key) is None for key in ("_index", "_id", "_seq_no", "_primary_term"))):
                        raise RuntimeError("条件更新缺少完整source/身份/版本，拒绝写入")
                    action = {"_index": hit["_index"], "_id": hit["_id"],
                              "if_seq_no": hit["_seq_no"], "if_primary_term": hit["_primary_term"]}
                    routing = hit.get("_routing")
                    if routing is None:
                        routing = (hit.get("fields", {}).get("_routing") or [None])[0]
                    if routing is not None:
                        action["routing"] = routing
                    document = self._apply_source_assignments(hit["_source"], update_fields)
                    size = len(serializer.dumps({"index": action})) + len(serializer.dumps(document)) + 2
                    if size > 8 * 1024 * 1024:
                        raise RuntimeError("条件更新单条source超过8MiB安全批次上限")
                    if operations and byte_count + size > 8 * 1024 * 1024:
                        chunks.append(operations)
                        operations = []
                        byte_count = 0
                    operations.extend(({"index": action}, document))
                    byte_count += size
                if operations:
                    chunks.append(operations)
                for operations in chunks:
                    bulk = _as_dict(client.bulk(operations=operations, refresh=True))
                    if bulk.get("error") or len(bulk.get("items") or []) != len(operations) // 2:
                        raise RuntimeError("条件更新bulk响应不完整；已成功部分不会回滚")
                    had_error = False
                    for pos, item in enumerate(bulk["items"]):
                        write = item.get("index") or {}
                        action = operations[pos * 2]["index"]
                        if any(key in write and write[key] != action[key] for key in ("_index", "_id")):
                            raise RuntimeError("条件更新bulk响应身份不匹配")
                        status = int(write.get("status", 500))
                        if status == 409:
                            had_error = True
                            result["version_conflicts"] += 1
                        elif status >= 300 or write.get("error"):
                            had_error = True
                            result["failures"].append({"status": status})
                        elif write.get("result") == "updated":
                            result["updated"] += 1
                        else:
                            raise RuntimeError("条件更新bulk返回未知result，不能确认更新")
                    if (bulk.get("errors") and not had_error) or result["failures"] or (conflicts == "abort" and result["version_conflicts"]):
                        raise RuntimeError("条件更新部分失败，已成功部分不会自动回滚")
                result["total"] += len(hits)
                after = next_after
                if requests_per_second > 0:
                    time.sleep(max(0, len(hits) / requests_per_second - (time.monotonic() - started)))
        finally:
            client.close_point_in_time(id=pit["id"])
        return result


    @staticmethod
    def _require_full_update_source(client: Any, indexes: Sequence[str]) -> None:
        """Never replace a document from incomplete stored source."""
        mappings = _as_dict(client.indices.get_mapping(index=list(indexes)))
        if not mappings:
            raise RuntimeError("条件更新未能确认完整source mapping")
        for entry in mappings.values():
            if not isinstance(entry, Mapping) or not isinstance(entry.get("mappings"), Mapping):
                raise RuntimeError("条件更新source mapping响应不完整")
            source = entry["mappings"].get("_source") or {}
            if not isinstance(source, Mapping):
                raise RuntimeError("条件更新source配置无效")
            if source.get("enabled") is False or source.get("includes") or source.get("excludes"):
                raise RuntimeError("条件更新要求迁移后的完整存储source，拒绝丢字段写入")

    def _conditional_update_responses(
        self, binding: SimpleNamespace, names: Sequence[str], query: Dict[str, Any],
        update_fields: Dict[str, Any], requests_per_second: int, conflicts: str,
    ) -> Iterator[Dict[str, Any]]:
        """Choose provider primitives while preserving caller contracts."""
        if self.router.resolve_provider(names[0]) == "serverless":
            maintenance_options = getattr(self, "_maintenance_update_options", None)
            client = (binding.es.options(request_timeout=maintenance_options["request_timeout_seconds"],
                                         max_retries=0, retry_on_timeout=False)
                      if maintenance_options else binding.es)
            self._require_full_update_source(client, names)
            yield self._checked_update_response(self._update_without_script(
                client, names, query, update_fields, requests_per_second, conflicts,
            ))
            return
        params: Dict[str, Any] = {}
        parts: List[str] = []
        for field, value in update_fields.items():
            param = "new_" + field.replace(".", "_")
            parts.append(self._painless_assignment(field, param))
            params[param] = value
        request = dict(
            index=list(names), query=query,
            script={"lang": "painless", "source": "; ".join(parts), "params": params},
            conflicts=conflicts, refresh=True, wait_for_completion=True,
            requests_per_second=requests_per_second,
        )
        maintenance_options = getattr(self, "_maintenance_update_options", None)
        response = (run_native_update(binding.es, request, **maintenance_options)
                    if maintenance_options else binding.es.update_by_query(**request))
        yield self._checked_update_response(response)

    def update_by_query(self, index_name: IndexNames, query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int = 500) -> Dict[str, Any]:
        """按query更新；更新错误可见，proceed冲突仍以原统计口径返回。"""
        merged = {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}
        for binding, names in self._group_indexes(index_name):
            for response in self._conditional_update_responses(
                binding, names, query, update_fields, requests_per_second, "proceed",
            ):
                if response.get("failures"):
                    raise RuntimeError("ES8 conditional update部分失败；已成功部分不会自动回滚")
                for key in ("updated", "total", "version_conflicts"):
                    merged[key] += int(response.get(key, 0) or 0)
                merged["failures"].extend(response.get("failures", []) or [])
        return merged


    def count_by_query(self, index_name: str, query: Dict[str, Any], require_complete: bool = False) -> int:
        """使用 ES8 count(query=) 统计文档数。"""
        client = self.get_client_by_index(index_name)
        last: Dict[str, Any] = {}
        for attempt in range(_SHARD_RETRY_TIMES):
            last = _as_dict(client.count(index=index_name, query=query))
            shards = last.get("_shards") or {}
            if not shards.get("failed"):
                if require_complete:
                    return complete_count(last)
                return int(last.get("count", 0) or 0)
            if attempt + 1 < _SHARD_RETRY_TIMES:
                time.sleep(_SHARD_RETRY_BACKOFF * (attempt + 1))
        raise RuntimeError(f"分片计数失败，已重试 {_SHARD_RETRY_TIMES} 次: index={index_name}")

    def agg_terms(self, index_name: str, query: Dict[str, Any], field: str, size: int = 1000, sub_aggs: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """使用 ES8 search(query=, aggs=) 返回 terms buckets。"""
        agg = {"terms": {"field": field, "size": size}}
        if sub_aggs:
            agg["aggs"] = sub_aggs
        response = self._search_request(
            self.get_client_by_index(index_name), [index_name], query, size=0,
            aggs={"grp": agg},
        )
        return response.get("aggregations", {}).get("grp", {}).get("buckets", []) or []

    def sample_by_query(
        self,
        index_name: str,
        query: Dict[str, Any],
        size: int = 10,
        includes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a small source-only sample using ES8 named search arguments."""
        body: Dict[str, Any] = {"query": query, "size": int(size)}
        if includes:
            body["_source"] = {"includes": includes}
        response = self._search_with_shard_check(index_name, body)
        return [
            dict(hit.get("_source") or {}, _id=hit.get("_id"))
            for hit in response.get("hits", {}).get("hits", []) or []
        ]

    def close(self) -> None:
        """关闭所有 provider client。"""
        self.router.close()


__all__ = ["EsSearchInterfaceES8"]
