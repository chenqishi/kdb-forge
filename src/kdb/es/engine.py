"""Elasticsearch 8.17 CRUD and native vector retrieval engine.

The old project used the Elasticsearch 7 ``body=`` API and a brute-force
``script_score`` over an unindexed ``dense_vector``. This module is the
rebuild boundary: normal requests use Elasticsearch 8 named parameters and
vector retrieval uses an indexed HNSW ``dense_vector``.
"""

from __future__ import annotations

import copy
import logging
from collections import OrderedDict
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

from kdb.es.client_router import IndexClientRouter

logger = logging.getLogger(__name__)

IndexNames = Optional[Union[str, List[str]]]
_CATEGORY_FIELDS = {
    "category_path", "category_ids", "cate1_name", "cate1_id", "cate2_name",
    "cate2_id", "cate3_name", "cate3_id", "cate4_name", "cate4_id", "cate_name",
}
_VECTOR_SOURCE_EXCLUDES = [
    "title_embedding", "content_embedding", "indexes.embedding", "image_indexes.embedding",
]


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


class RoutedLegacyEngine:
    """按 index 路由的 ES 8.17 引擎。

    类名保留是为了兼容上层 import，但生产实现已经不再实例化旧的
    ``EsSearchInterfaceOri``。跨 provider 的请求在本类分组，查询、mapping、
    CRUD 均使用 ES 8.17 API；dual 模式分别执行 BM25 与 native KNN 两路并去重。
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        index_name: Optional[str] = None,
        hosts: Optional[Union[str, List[str]]] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vector_fields: Optional[Dict[str, int]] = None,
        extra_params: Optional[Dict[str, Any]] = None,
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
        self._ensure_index_on_init = ensure_index
        self._impls: "OrderedDict[str, SimpleNamespace]" = OrderedDict()
        self._impl: Optional[SimpleNamespace] = None
        self._impl_for(self.index_name)

    # ------------------------------------------------------------------
    # Index routing and mapping
    # ------------------------------------------------------------------
    def _impl_for(self, index_name: str) -> SimpleNamespace:
        """创建并缓存一个 index 的兼容 binding，不再构造旧 ES7 实现。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        if index not in self._impls:
            binding = SimpleNamespace(index_name=index, es=self.router.get_client_by_index(index))
            self._impls[index] = binding
            if self._ensure_index_on_init:
                self._ensure_index(index)
            if self._impl is None and index == self.index_name:
                self._impl = binding
        return self._impls[index]

    def _group_indexes(self, index_names: IndexNames) -> List[Tuple[SimpleNamespace, List[str]]]:
        """按 provider 分组索引，确保每组只使用对应连接池。"""
        names = _split_index_names(index_names, self.index_name)
        grouped: "OrderedDict[str, List[str]]" = OrderedDict()
        for name in names:
            grouped.setdefault(self.router.resolve_provider(name), []).append(name)
        return [(self._impl_for(group[0]), group) for group in grouped.values()]

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
                "title_embedding": {"type": "dense_vector", "dims": dims, "index": False},
                "content_embedding": {"type": "dense_vector", "dims": dims, "index": False},
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

    def _ensure_index(self, index_name: str) -> None:
        """创建 native KNN 索引或拒绝不兼容的旧 ES7 mapping。"""
        index = str(index_name or "").strip().lower()
        if not index:
            raise ValueError("index_name 不能为空")
        binding = self._impls.get(index) or self._impl_for(index)
        client = binding.es
        if not bool(client.indices.exists(index=index)):
            client.indices.create(
                index=index,
                settings={"number_of_shards": 3, "number_of_replicas": 1, "refresh_interval": "30s"},
                mappings=self._build_mapping(),
            )
            return
        mappings = _as_dict(client.indices.get_mapping(index=index))
        current = mappings.get(index) or (next(iter(mappings.values())) if mappings else {})
        vector_mapping = self._existing_vector_mapping(current)
        if (
            vector_mapping.get("type") != "dense_vector"
            or vector_mapping.get("index") is not True
            or int(vector_mapping.get("dims", -1)) != self._vector_dimension()
        ):
            raise RuntimeError(
                f"索引 {index!r} 不是 ES8 native KNN mapping："
                "indexes.embedding 必须是 index=true 的 dense_vector。"
                "旧 ES7/script_score 索引不能原地升级，请新建 ES8 索引并 reindex。"
            )

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

    def _build_knn_clause(
        self,
        query_vector: Sequence[float],
        vector_field: str = "indexes.embedding",
        k: int = 10,
        num_candidates: Optional[int] = None,
        filter_query: Optional[Dict[str, Any]] = None,
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
            return {"nested": {"path": field.split(".", 1)[0], "score_mode": "max", "query": {"knn": knn}}}
        return {"knn": knn}

    def _build_search_query(
        self,
        query: Mapping[str, Any],
        include_text: bool = True,
        include_vector: bool = True,
        vector_k: int = 10,
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
                should.append(self._build_knn_clause(vector, k=vector_k, filter_query=filter_query))
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
    def _hits(response: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """把 ES hit 转成旧上层使用的文档结构。"""
        docs = []
        for hit in response.get("hits", {}).get("hits", []) or []:
            doc = {"_id": hit.get("_id"), "score": hit.get("_score", 0)}
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
    ) -> Dict[str, Any]:
        """使用 ES8 named parameters 发起 search 请求。"""
        kwargs: Dict[str, Any] = {"index": ",".join(indexes), "query": query, "size": int(size)}
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
        return _as_dict(client.search(**kwargs))

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
        return _as_dict(client.search(**kwargs))

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
        ok = True
        for binding, names in self._group_indexes(index_names):
            for index in names:
                response = binding.es.update(index=index, id=str(data_id), doc=copy.deepcopy(data))
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

    def insert_with_vectors(self, data: Dict[str, Any], vectors: Dict[str, List[float]], index_name: Optional[str] = None) -> bool:
        """用 ES8 index(document=...) 写入带多个根向量的文档。"""
        payload = copy.deepcopy(data)
        if "_id" not in payload:
            return False
        for field, vector in vectors.items():
            if len(vector) != self._vector_dimension():
                return False
            payload[self._canonical_vector_field(field)] = vector
        doc_id = str(payload.pop("_id"))
        ok = True
        for binding, names in self._group_indexes(index_name):
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
            k=max(size, 10),
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
        if dual:
            routes = [("bm25", True, False, max(1, size // 2)), ("vector", False, True, max(1, size // 2))]
        elif mode == "bm25":
            routes = [("bm25", True, False, size)]
        elif mode == "vector":
            routes = [("vector", False, True, size)]
        else:
            routes = [("single", has_text, has_vector, size)]
        merged: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        total = 0
        for route_name, include_text, include_vector, route_size in routes:
            route_query = self._build_search_query(query, include_text=include_text, include_vector=include_vector, vector_k=max(route_size, 10))
            response = self._search_request(binding.es, names, route_query, size=route_size)
            route_total = self._total(response)
            total = max(total, route_total) if dual else route_total
            for hit in response.get("hits", {}).get("hits", []) or []:
                key = f"{hit.get('_index', '')}:{hit.get('_id')}"
                if key not in merged:
                    doc = {"_id": hit.get("_id"), "score": hit.get("_score", 0)}
                    doc.update(hit.get("_source") or {})
                    merged[key] = doc
                else:
                    for field, value in (hit.get("_source") or {}).items():
                        merged[key].setdefault(field, value)
            logger.debug("native recall route=%s index=%s hits=%d", route_name, names, len(response.get("hits", {}).get("hits", []) or []))
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
        docs: List[Dict[str, Any]] = []
        total = 0
        remaining_offset = max(0, (page_num - 1) * size)
        for binding, names in self._group_indexes(index_names):
            for name in names:
                response = self._search_request(
                    binding.es, [name], self._build_search_query(query, include_text=True, include_vector=False),
                    size=size, from_=remaining_offset, min_score=score_threshold,
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
                        response = _as_dict(binding.es.scroll(scroll_id=scroll_id, scroll=scroll_timeout))
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
            response = _as_dict(binding.es.search(index=",".join(names), query=self._filter_query(extra_query or {}), size=0, aggs={"unique_vals": {"terms": {"field": field_name, "size": size}}}))
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
        """使用 ES8 update_by_query(query=, script=) 批量更新文档。"""
        if not update_value_dict:
            return True
        # 旧 update_value 的 conditions 是 AND 关系；search_multi 的 attribute list
        # 才是 OR 关系，不能直接复用同一个 list 解析入口。
        condition_clauses: List[Dict[str, Any]] = []
        for condition in conditions or []:
            clauses, _ = self._attribute_clauses(condition)
            condition_clauses.extend(clauses)
        query = {"bool": {"must": condition_clauses}} if condition_clauses else {"match_all": {}}
        params: Dict[str, Any] = {}
        parts: List[str] = []
        for field, value in update_value_dict.items():
            param = "new_" + field.replace(".", "_")
            parts.append(f"ctx._source['{field}'] = params.{param}")
            params[param] = value
        script = {"lang": "painless", "source": "; ".join(parts), "params": params}
        ok = True
        for binding, names in self._group_indexes(index_name):
            response = binding.es.update_by_query(index=names, query=query, script=script, conflicts="proceed", refresh=True, wait_for_completion=True)
            ok = ok and not (_response_value(response, "failures", []) or [])
        return ok

    def update_by_query(self, index_name: IndexNames, query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int = 500) -> Dict[str, Any]:
        """使用 ES8 update_by_query named parameters 批量更新。"""
        params: Dict[str, Any] = {}
        parts: List[str] = []
        for field, value in update_fields.items():
            param = "new_" + field.replace(".", "_")
            parts.append(f"ctx._source['{field}'] = params.{param}")
            params[param] = value
        merged = {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}
        for binding, names in self._group_indexes(index_name):
            response = _as_dict(binding.es.update_by_query(index=names, query=query, script={"lang": "painless", "source": "; ".join(parts), "params": params}, conflicts="proceed", refresh=True, wait_for_completion=True, requests_per_second=requests_per_second))
            for key in ("updated", "total", "version_conflicts"):
                merged[key] += int(response.get(key, 0) or 0)
            merged["failures"].extend(response.get("failures", []) or [])
        return merged

    def count_by_query(self, index_name: str, query: Dict[str, Any]) -> int:
        """使用 ES8 count(query=) 统计文档数。"""
        return int(_response_value(self.get_client_by_index(index_name).count(index=index_name, query=query), "count", 0) or 0)

    def agg_terms(self, index_name: str, query: Dict[str, Any], field: str, size: int = 1000, sub_aggs: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """使用 ES8 search(query=, aggs=) 返回 terms buckets。"""
        agg = {"terms": {"field": field, "size": size}}
        if sub_aggs:
            agg["aggs"] = sub_aggs
        response = _as_dict(self.get_client_by_index(index_name).search(index=index_name, query=query, size=0, aggs={"grp": agg}))
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


__all__ = ["RoutedLegacyEngine"]
