"""Compatibility methods for the old SearchDataInterface.

The rebuild keeps the old service contract at this boundary.  The method names and
return shapes remain stable while all Elasticsearch traffic is delegated to the
ES 8.17 routed engine.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import quote

from kdb.crud.models import SCHEMA_FIELDS
from kdb.legacy_bridge import ensure_legacy_on_path

logger = logging.getLogger(__name__)


class LegacySearchDataInterfaceMixin:
    """Expose the old SearchDataInterface API on the rebuilt service."""

    FROM_TYPE_SCOPE = ["document", "html", "manual"]
    FILE_NAME_FIELD = "ext_info.from_file_name"
    FILE_NAME_KEYWORD = "ext_info.from_file_name.keyword"
    SUPERSEDES_FIELD_KEYWORD = "ext_info.supersedes_file_name.keyword"
    KEYWORD_IGNORE_ABOVE = 256
    MAX_WILDCARD_FRAGMENT = 48
    DICE_THRESHOLD = 0.9

    def _init_legacy_compat(self, legacy_config: Optional[Mapping[str, Any]] = None) -> None:
        """Initialise attributes expected by old callers."""
        config = dict(legacy_config or {})
        self._legacy_config = config
        self.engine = getattr(self._repo, "_engine", self._repo)
        self.embedding_tools = self._embedding
        self.multimodal_prefix = self._multimodal_prefix
        self.is_need_llm = bool(config.get("is_need_llm", False))
        self.check_duplicate = bool(config.get("check_duplicate", True))
        self.category_service_url = config.get("category_service_url", "") or ""
        self.category_update_time_interval = config.get(
            "category_update_time_interval", 36000
        )
        self.category_update_time_dict: Dict[str, float] = {}
        self.all_client_category_dict: Dict[str, Dict[str, Any]] = {}
        self.doc_schema_field = set(SCHEMA_FIELDS)
        self.simility_tools = None

    @staticmethod
    def _load_json(path: str) -> Dict[str, Any]:
        """读取兼容配置文件。"""
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def _build_es8_config(
        cls, config_path: str, index_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """把旧单地址 ES 配置规范化为 ES8.17 路由配置。"""
        raw = cls._load_json(config_path)
        if raw.get("providers"):
            result = dict(raw)
            result.setdefault("es_version", "8.17")
            if index_name:
                result["index_name"] = index_name
            return result

        hosts = raw.get("hosts") or raw.get("host")
        if not hosts:
            raise ValueError(f"ES 配置缺少 hosts: {config_path}")
        if isinstance(hosts, str):
            hosts = [hosts]
        provider = {
            "hosts": hosts,
            "username": raw.get("username"),
            "password": raw.get("password"),
            "verify_certs": raw.get("verify_certs", False),
        }
        return {
            "es_version": "8.17",
            "index_name": index_name or raw.get("index_name"),
            "vector_fields": raw.get("vector_fields") or {"indexes_embedding": 1024},
            "default_provider": "serverless",
            "providers": {"serverless": provider},
            "index_routes": {},
            "extra_params": raw.get("extra_params") or {},
        }

    def load_search_engine(self, config_path: str, **kwargs: Any) -> Any:
        """Construct the ES8.17 engine while retaining the old loader signature."""
        from kdb.es.engine import RoutedLegacyEngine

        index_name = kwargs.pop("index_name", None)
        config = self._build_es8_config(config_path, index_name=index_name)
        vector_fields = kwargs.pop("vector_fields", None)
        if vector_fields:
            config["vector_fields"] = vector_fields
        extra_params = kwargs.pop("extra_params", None)
        if extra_params:
            config.setdefault("extra_params", {}).update(extra_params)
        if kwargs:
            provider = config.setdefault("providers", {}).setdefault(
                config.get("default_provider", "serverless"), {}
            )
            for key in ("hosts", "username", "password", "verify_certs"):
                if key in kwargs:
                    provider[key] = kwargs[key]
        return RoutedLegacyEngine(config=config, index_name=index_name)

    def load_category_map_dict(self, client: str, user: Any = None) -> Any:
        """Load and cache a client's category tree using the legacy HTTP contract."""
        try:
            if (
                client in self.category_update_time_dict
                and time.time() - self.category_update_time_dict[client]
                < self.category_update_time_interval
            ):
                return None
            if not self.category_service_url:
                return None

            import requests

            params = {"client": client}
            if user:
                params["user"] = user
            response = requests.get(self.category_service_url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            if response.status_code != 200:
                logger.error("获取类目数据失败: %s", result.get("message", "未知错误"))
                return {"name_map_dict": {}, "id_map_dict": {}}

            maps = {"name_map_dict": {}, "id_map_dict": {}}

            def traverse(node: Dict[str, Any], parents: List[Dict[str, Any]]) -> None:
                current = {
                    "category_name": node.get("categoryName"),
                    "category_id": node.get("categoryId"),
                    "level": node.get("level", 0),
                }
                chain = parents + [current]
                if current["category_name"]:
                    path = "-".join(item["category_name"] for item in chain)
                    maps["name_map_dict"][path] = chain
                if current["category_id"]:
                    maps["id_map_dict"][current["category_id"]] = chain
                for child in node.get("children", []) or []:
                    traverse(child, chain)

            for category in result.get("data", []) or []:
                traverse(category, [])
            self.category_update_time_dict[client] = time.time()
            self.all_client_category_dict[client] = maps
            return True
        except Exception as exc:  # pragma: no cover - HTTP failure path
            logger.warning("加载类目字典失败: %s", exc)
            return None

    def map_cate_name_to_id(self, client: str, category_name: str) -> Any:
        """Map a category path/name to its leaf ID."""
        current = self.all_client_category_dict.get(client, {}).get("name_map_dict", {})
        if category_name not in current:
            self.load_category_map_dict(client)
        nodes = self.all_client_category_dict.get(client, {}).get("name_map_dict", {}).get(
            category_name, []
        )
        return nodes[-1]["category_id"] if nodes else None

    def get_category_parent_chain(
        self, client: str, cate_id: str = None, cate_name: str = None
    ) -> List[Dict[str, Any]]:
        """Return the cached or freshly loaded category parent chain."""
        if not cate_id and not cate_name:
            return []
        maps = self.all_client_category_dict.get(client, {})
        if cate_id:
            chain = maps.get("id_map_dict", {}).get(cate_id, [])
        else:
            chain = maps.get("name_map_dict", {}).get(cate_name, [])
        if chain:
            return chain
        self.load_category_map_dict(client)
        maps = self.all_client_category_dict.get(client, {})
        if cate_id:
            return maps.get("id_map_dict", {}).get(cate_id, [])
        return maps.get("name_map_dict", {}).get(cate_name, [])

    def _apply_category_defaults(self, data: Dict[str, Any], is_new: bool) -> None:
        """Normalize explicit categories and defaults; inference belongs to mining."""
        raw_infos = data.get("category_infos")
        valid_infos: List[Dict[str, Any]] = []
        if raw_infos:
            for raw in raw_infos:
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                if item.get("category_id") in (None, "") and item.get("categoryId") not in (None, ""):
                    item["category_id"] = item.pop("categoryId")
                if item.get("category_name") in (None, "") and item.get("categoryName") not in (None, ""):
                    item["category_name"] = item.pop("categoryName")
                if item.get("category_id") not in (None, ""):
                    item["category_id"] = str(item["category_id"])
                if item.get("category_name") not in (None, ""):
                    item["category_name"] = str(item["category_name"]).strip()
                if item.get("category_id") or item.get("category_name"):
                    valid_infos.append(item)
            data["category_infos"] = valid_infos

        client = data.get("client") or data.get("ext_info", {}).get("client") or data.get("platform")
        primary = None
        parent_chain: List[Dict[str, Any]] = []
        if client:
            for item in sorted(valid_infos, key=lambda value: value.get("score", 0), reverse=True):
                chain = self.get_category_parent_chain(
                    client, cate_id=item.get("category_id"), cate_name=item.get("category_name")
                )
                if chain:
                    primary, parent_chain = item, chain
                    break

        if parent_chain and primary:
            leaf = parent_chain[-1]
            primary.setdefault("category_id", str(leaf.get("category_id") or ""))
            primary.setdefault("category_name", leaf.get("category_name"))
            names = [node["category_name"] for node in parent_chain]
            category = {
                "category_path": "-".join(names),
                "category_ids": [node["category_id"] for node in parent_chain],
            }
            for index, node in enumerate(parent_chain, start=1):
                category[f"cate{index}_name"] = node["category_name"]
                category[f"cate{index}_id"] = node["category_id"]
            data["primary_category"] = category

        if is_new and not data.get("primary_category"):
            try:
                ensure_legacy_on_path()
                from knowledge_interface_tools.knowledge_tools import (
                    build_default_category_infos,
                    build_default_primary_category,
                )

                data["primary_category"] = build_default_primary_category()
                if not data.get("category_infos"):
                    data["category_infos"] = build_default_category_infos()
            except Exception:  # pragma: no cover - fallback when legacy package unavailable
                data["primary_category"] = {
                    "category_path": "默认分组",
                    "category_ids": ["1"],
                    "cate1_name": "默认分组",
                    "cate1_id": "1",
                }
                if not data.get("category_infos"):
                    data["category_infos"] = [{
                        "category_id": "1", "category_name": "默认分组",
                        "score": 1.0, "source": "default",
                    }]

    def find_duplicates(
        self,
        data: Dict[str, Any],
        topK: int = 5,
        is_need_llm: bool = True,
        index_name: str = None,
        exclude_self: bool = False,
        is_only_title: bool = False,
        basic_threshold: float = 0.7,
        title_basic_threshold: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """Find duplicates with the old candidate and similarity workflow."""
        processed = data.copy()
        if not self.process_one_data(processed):
            logger.error("处理待查重数据失败")
            return []
        query: Dict[str, Any] = {
            "query": f"{processed.get('title', '')} {processed.get('content', '')}"
        }
        if processed.get("indexes") and processed["indexes"][0].get("embedding"):
            query["vector"] = {"value": processed["indexes"][0]["embedding"]}
        query["attribute"] = {
            "data_type": processed.get("data_type", "unkonw"),
            "platform": processed.get("platform", "unkonw"),
        }
        candidates = self.search_data(query, size=topK, index_names=index_name)
        duplicates = []
        for candidate in candidates:
            if candidate.get("_id") == processed.get("_id"):
                if not exclude_self:
                    duplicates.append(candidate)
                continue
            if self._get_simility_tools().is_simility_knowledge(
                processed,
                candidate,
                is_need_llm=is_need_llm,
                is_only_title=is_only_title,
                basic_threshold=basic_threshold,
                title_basic_threshold=title_basic_threshold,
            ):
                duplicates.append(candidate)
        return duplicates

    def process_one_data(self, data: Dict[str, Any], index_name: str = None) -> bool:
        """Mutate a document in place using the rebuilt full preparation pipeline."""
        try:
            prepared = self._prepare_document(data, index_name=index_name)
            if prepared is not data:
                data.clear()
                data.update(prepared)
            return True
        except Exception:
            logger.error("处理数据失败: %s", traceback.format_exc())
            return False

    def insert_data(
        self,
        data: Dict[str, Any],
        check_duplicate: bool = None,
        index_name: str = None,
        is_update_data: bool = False,
        is_only_title: bool = False,
        basic_threshold: float = 0.7,
        title_basic_threshold: float = 0.95,
        refresh_imm: bool = False,
        is_need_llm: bool = None,
    ) -> Tuple[bool, str]:
        """Insert with the old processing, deduplication, and return contract."""
        check_duplicate = self.check_duplicate if check_duplicate is None else check_duplicate
        prepared = copy.deepcopy(data)
        if not self.process_one_data(prepared, index_name=index_name):
            return False, "数据处理失败"
        llm = self.is_need_llm if is_need_llm is None else is_need_llm
        if check_duplicate:
            duplicates = self.find_duplicates(
                prepared,
                is_need_llm=llm,
                index_name=index_name,
                exclude_self=True,
                is_only_title=is_only_title,
                basic_threshold=basic_threshold,
                title_basic_threshold=title_basic_threshold,
            )
            if duplicates:
                duplicate_ids = [item["_id"] for item in duplicates]
                if is_update_data:
                    try:
                        self.engine.update_value(
                            index_name=index_name,
                            update_value_dict={
                                "del_flag": 1,
                                "del_reason": f"cover_by_new {prepared.get('_id')}",
                            },
                            conditions=[{"_id": duplicate_ids}],
                        )
                    except Exception as exc:
                        logger.error("软删除重复数据失败: %s", exc)
                else:
                    return False, "数据重复"
        ok = self.engine.insert(prepared, index_names=index_name, refresh_imm=refresh_imm)
        return bool(ok), ""

    def batch_insert_data(
        self, data_list: List[Dict[str, Any]], check_duplicate: bool = True
    ) -> List[Tuple[bool, str]]:
        """Insert each item in order using the old batch result shape."""
        return [self.insert_data(data, check_duplicate) for data in data_list]

    def update_data(self, data_id: str, data: Dict[str, Any]) -> bool:
        """Update a document using the old low-level patch semantics."""
        return self.engine.update(data_id, data)

    def delete_data(
        self,
        data_id: str,
        index_names: Optional[Union[str, List[str]]] = None,
        refresh: bool = False,
    ) -> bool:
        """Delete a document using the old signature."""
        return self.engine.delete(data_id, index_names=index_names, refresh=refresh)

    def search_data(
        self,
        query: Dict[str, Any],
        size: Optional[int] = None,
        index_names: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Run the old raw search entry point."""
        return self.engine.search(query, 10 if size is None else size, index_names=index_names)

    def update_data_value(
        self, index_name: str, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]]
    ) -> bool:
        """Update fields matching the old AND-condition list."""
        return self.engine.update_value(index_name, update_value_dict, conditions)

    def get_unique_values(
        self,
        index_name: str,
        field_name: str,
        size: int = 10000,
        include_doc_count: bool = False,
        extra_query: Optional[Dict[str, Any]] = None,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """Return terms aggregation values using the old signature."""
        return self.engine.get_unique_values(
            index_name, field_name, size, include_doc_count, extra_query
        )

    def join_multimodal_contents(self, multimodal_contents: List[Dict[str, Any]]) -> str:
        """Expose the old public multimodal concatenation method."""
        return self._join_multimodal_contents(multimodal_contents)

    def search_data_by_query(
        self,
        query: str,
        index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Expose the old single-query semantic search method."""
        return self.search_text(
            query,
            index_name=index_names,
            condition_dicts=condition_dicts,
            size=size,
            search_type=search_type,
            data_type=data_type,
            use_synonyms=use_synonyms,
        )

    def search_data_by_multi_query(
        self,
        query_list: List[str],
        index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Expose the old multi-query search and its threaded fallback."""
        if not query_list:
            logger.warning("query_list为空，返回空结果")
            return [], 0
        embeddings = []
        for query in query_list:
            if query:
                embedding = self.embedding_tools.text2embedding(query)
                if embedding is not None:
                    embeddings.append({"value": embedding})
        query: Dict[str, Any] = {
            "query": query_list,
            "vector": embeddings if embeddings else None,
        }
        indexes = None
        if index_names:
            indexes = index_names.split(",") if isinstance(index_names, str) else list(index_names)
        if not condition_dicts:
            condition_dicts = [
                {"quality_level": ["high"], "data_type": ["qa"]},
                {"audit_result": [1], "data_type": ["qa"]},
            ]
        for condition in condition_dicts:
            if "audit_result" not in condition:
                condition["audit_result"] = [1, -1]
        query["attribute"] = condition_dicts
        try:
            docs, total = self.engine.search_multi(query, index_names=indexes, size=size * 2)
            for doc in docs:
                max_similarity = 0
                for index, text_query in enumerate(query_list):
                    if text_query:
                        query_embedding = embeddings[index]["value"] if index < len(embeddings) else None
                        if query_embedding is not None:
                            max_similarity = max(
                                max_similarity,
                                self._cal_similarity(
                                    text_query,
                                    query_embedding,
                                    doc,
                                    search_type=search_type,
                                    data_type=data_type,
                                    use_synonyms=use_synonyms,
                                ),
                            )
                doc["similarity"] = max_similarity
                self.render_multimodal_urls(doc)
            return docs, total
        except Exception:
            logger.error("多查询搜索失败，切换线程回退: %s", traceback.format_exc())
            return self._search_data_by_multi_query_threading(
                query_list, indexes, condition_dicts, size, search_type, data_type, use_synonyms
            )

    def _search_data_by_multi_query_threading(
        self,
        query_list: List[str],
        index_names: Optional[Union[str, List[str]]] = None,
        condition_dicts: List[Dict[str, Any]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Threaded fallback retained for callers that rely on the old behavior."""
        def one(query: str) -> Tuple[List[Dict[str, Any]], int]:
            return self.search_data_by_query(
                query, index_names, condition_dicts, size, search_type, data_type, use_synonyms
            )

        all_results: List[Dict[str, Any]] = []
        totals: List[int] = []
        with ThreadPoolExecutor(max_workers=min(len(query_list), 10)) as executor:
            futures = {executor.submit(one, query): query for query in query_list if query}
            for future in as_completed(futures):
                try:
                    results, total = future.result()
                    all_results.extend(results)
                    totals.append(total)
                except Exception as exc:
                    logger.error("查询失败: %s", exc)
        seen, merged = set(), []
        for doc in all_results:
            doc_id = doc.get("_id")
            if doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc)
        merged.sort(key=lambda item: item.get("similarity", 0), reverse=True)
        return merged[:size], max(totals) if totals else 0

    def web_search_data(
        self,
        query: str,
        client: str = None,
        index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None,
        page_size: int = None,
        page_num: int = 1,
        score_threshold: float = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Expose the old web-search request contract over ES8 BM25 pagination."""
        if query:
            search_query: Dict[str, Any] = {
                "query": query,
                "vector": {"value": self.embedding_tools.text2embedding(query)},
            }
        else:
            search_query = {}
        indexes = None
        if index_names:
            indexes = index_names.split(",") if isinstance(index_names, str) else list(index_names)
        first_index = indexes[0] if indexes else None
        condition_dicts = condition_dicts or []
        client = client or first_index
        for condition in condition_dicts:
            category_ids = []
            if "category_names" in condition:
                names = condition["category_names"]
                names = names if isinstance(names, list) else [names]
                category_ids.extend(
                    value for value in (self._category.map_cate_name_to_id(client, name) for name in names) if value
                )
                condition.pop("category_names")
            if "category_ids" in condition:
                values = condition["category_ids"]
                category_ids.extend(values if isinstance(values, list) else [values])
                condition.pop("category_ids")
            if category_ids:
                condition["category_ids"] = category_ids
        search_query["attribute"] = condition_dicts
        page_size = page_size or 10000
        docs, total = self.engine.search_multi_by_page(
            search_query,
            index_names=indexes,
            size=page_size,
            page_num=page_num,
            score_threshold=score_threshold,
        )
        for doc in docs:
            self.render_multimodal_urls(doc)
            if "score" in doc:
                doc["score"] = min(doc["score"] / 5.0, 1.0)
        return docs, total

    @staticmethod
    def _bigrams(text: str) -> set:
        """Return lowercase character bigrams."""
        value = (text or "").strip().lower()
        return {value[index : index + 2] for index in range(len(value) - 1)} or ({value} if value else set())

    @classmethod
    def dice_similarity(cls, a: str, b: str) -> float:
        """Calculate the old character-bigram Dice similarity."""
        left, right = cls._bigrams(a), cls._bigrams(b)
        if not left or not right:
            return 1.0 if (a or "") == (b or "") else 0.0
        return 2 * len(left & right) / (len(left) + len(right))

    @staticmethod
    def _escape_wildcard(text: str) -> str:
        """Escape wildcard characters in a file name."""
        return (text or "").replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")

    def _scope_filters(self) -> List[Dict[str, Any]]:
        """Build the old file-operation scope filters."""
        return [{"term": {"del_flag": 0}}, {"terms": {"from_type_norm": self.FROM_TYPE_SCOPE}}]

    def _build_file_query(
        self,
        file_names: List[str],
        data_types: Optional[List[str]] = None,
        audit_results: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Build the old file-name query including superseded names."""
        must = self._scope_filters()
        must.append(
            {
                "bool": {
                    "should": [
                        {"terms": {self.FILE_NAME_KEYWORD: list(file_names)}},
                        {"terms": {self.SUPERSEDES_FIELD_KEYWORD: list(file_names)}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
        if data_types:
            must.append({"terms": {"data_type": list(data_types)}})
        if audit_results:
            must.append({"terms": {"audit_result": list(audit_results)}})
        return {"bool": {"must": must}}

    def list_file_names(self, index_name: str, keyword: str = None, size: int = 200) -> List[Dict[str, Any]]:
        """List real source file names in the old scoped shape."""
        must = self._scope_filters()
        if keyword:
            fragment = self._escape_wildcard(keyword)[: self.MAX_WILDCARD_FRAGMENT]
            must.append({"wildcard": {self.FILE_NAME_KEYWORD: {"value": f"*{fragment}*", "case_insensitive": True}}})
        buckets = self.engine.agg_terms(
            index_name,
            {"bool": {"must": must}},
            self.FILE_NAME_KEYWORD,
            size=size,
            sub_aggs={"by_type": {"terms": {"field": "data_type", "size": 10}}},
        )
        result = []
        for bucket in buckets:
            raw = (bucket.get("sub") or {}).get("by_type") or bucket.get("by_type") or {}
            if isinstance(raw, dict) and "buckets" in raw:
                raw = {item["key"]: item["doc_count"] for item in raw["buckets"]}
            result.append({"value": bucket.get("key"), "doc_count": bucket.get("doc_count", 0), "type_count": raw})
        return result

    def resolve_file_name(self, index_name: str, name: str, match_mode: str = "exact") -> Dict[str, Any]:
        """Resolve a user file name with the old exact/fuzzy contract."""
        name = (name or "").strip()
        if not name:
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0, "reason": "文件名为空"}
        if len(name) > self.KEYWORD_IGNORE_ABOVE:
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0, "reason": f"文件名超过 {self.KEYWORD_IGNORE_ABOVE} 字符，未被索引为 keyword，无法按文件名匹配"}
        if match_mode == "exact":
            count = self.engine.count_by_query(index_name, self._build_file_query([name]))
            if count:
                return {"matched": True, "matched_name": name, "doc_count": count, "dice": 1.0, "reason": None}
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0, "reason": "精确匹配无结果"}
        if match_mode != "fuzzy":
            return {"matched": False, "matched_name": None, "doc_count": 0, "dice": 0.0, "reason": "match_mode 只能是 exact 或 fuzzy"}
        escaped = self._escape_wildcard(name)
        fragment = escaped[: self.MAX_WILDCARD_FRAGMENT]
        prefix = escaped[: max(4, min(len(escaped) * 3 // 5, self.MAX_WILDCARD_FRAGMENT))]
        shoulds = [
            {"wildcard": {self.FILE_NAME_KEYWORD: {"value": f"*{fragment}*", "case_insensitive": True}}},
            {"match": {self.FILE_NAME_FIELD: {"query": name}}},
            {"match": {self.FILE_NAME_FIELD: {"query": name, "fuzziness": "AUTO"}}},
        ]
        if prefix and prefix != fragment:
            shoulds.append({"wildcard": {self.FILE_NAME_KEYWORD: {"value": f"*{prefix}*", "case_insensitive": True}}})
        query = {"bool": {"must": self._scope_filters(), "should": shoulds, "minimum_should_match": 1}}
        best = None
        for bucket in self.engine.agg_terms(index_name, query, self.FILE_NAME_KEYWORD, size=80):
            candidate = (self.dice_similarity(name, bucket["key"]), bucket["key"], bucket["doc_count"])
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best and best[0] >= self.DICE_THRESHOLD:
            return {"matched": True, "matched_name": best[1], "doc_count": best[2], "dice": round(best[0], 4), "reason": None}
        return {"matched": False, "matched_name": None, "doc_count": 0, "dice": round(best[0], 4) if best else 0.0, "reason": f"模糊匹配最高相似度 {best[0] if best else 0.0:.4f} 未达阈值 {self.DICE_THRESHOLD}"}

    def preview_delete_by_file(
        self,
        index_name: str,
        file_names: List[str],
        match_mode: str = "exact",
        data_types: Optional[List[str]] = None,
        audit_results: Optional[List[int]] = None,
        sample_size: int = 10,
    ) -> Dict[str, Any]:
        """Preview file-name soft deletion without changing ES."""
        by_file, warnings, resolved = [], [], []
        for raw in file_names:
            match = self.resolve_file_name(index_name, raw, match_mode)
            entry = {"input_name": raw, "matched": match["matched"], "matched_name": match["matched_name"], "dice": match["dice"], "count": match["doc_count"], "type_count": {}, "audit_count": {}}
            if not match["matched"]:
                entry["reason"] = match["reason"]
                warnings.append(f"「{raw}」未匹配到：{match['reason']}")
            else:
                if match_mode == "fuzzy" and match["matched_name"] != raw:
                    warnings.append(f"「{raw}」模糊匹配到「{match['matched_name']}」(相似度 {match['dice']:.4f}，{match['doc_count']} 条)，请确认")
                query = self._build_file_query([match["matched_name"]], data_types, audit_results)
                entry["count"] = self.engine.count_by_query(index_name, query)
                for bucket in self.engine.agg_terms(index_name, query, "data_type", size=10):
                    entry["type_count"][bucket["key"]] = bucket["doc_count"]
                for bucket in self.engine.agg_terms(index_name, query, "audit_result", size=10):
                    entry["audit_count"][str(bucket["key"])] = bucket["doc_count"]
                resolved.append(match["matched_name"])
            by_file.append(entry)
        total, type_count, samples = 0, {}, []
        if resolved:
            query = self._build_file_query(resolved, data_types, audit_results)
            total = self.engine.count_by_query(index_name, query)
            for bucket in self.engine.agg_terms(index_name, query, "data_type", size=10):
                type_count[bucket["key"]] = bucket["doc_count"]
            if sample_size:
                samples = self.engine.sample_by_query(index_name, query, size=sample_size, includes=["title", "content", "data_type", "audit_result", "ext_info.from_file_name", "from_type_norm"])
                for sample in samples:
                    sample["content"] = (sample.get("content") or "")[:120]
        return {"total_count": total, "by_file": by_file, "type_count": type_count, "samples": samples, "warnings": warnings, "resolved_names": resolved}

    def delete_by_file(
        self,
        index_name: str,
        file_names: List[str],
        match_mode: str = "exact",
        data_types: Optional[List[str]] = None,
        audit_results: Optional[List[int]] = None,
        snapshot_dir: str = "data/deleted_snapshots",
    ) -> Dict[str, Any]:
        """Soft-delete matching files after writing the old JSONL snapshot."""
        preview = self.preview_delete_by_file(index_name, file_names, match_mode, data_types, audit_results, sample_size=0)
        resolved = preview["resolved_names"]
        if not resolved:
            return {"success": False, "deleted_count": 0, "snapshot_path": None, "message": "没有匹配到任何文件名，未执行删除；" + "；".join(preview["warnings"])}
        query = self._build_file_query(resolved, data_types, audit_results)
        snapshot_path = self._dump_snapshot(index_name, query, snapshot_dir)
        result = self.engine.update_by_query(index_name, query, {"del_flag": 1})
        message = f"已软删除 {result['updated']} 条"
        if result.get("version_conflicts"):
            message += f"（版本冲突 {result['version_conflicts']} 条已跳过）"
        return {"success": True, "deleted_count": result["updated"], "snapshot_path": snapshot_path, "message": message}

    def _dump_snapshot(self, index_name: str, query: Dict[str, Any], snapshot_dir: str) -> Optional[str]:
        """Write a vector-free JSONL snapshot before a file soft-delete."""
        os.makedirs(snapshot_dir, exist_ok=True)
        path = os.path.join(snapshot_dir, f"{index_name}_{time.strftime('%Y%m%d_%H%M%S')}.jsonl")
        total = self.engine.count_by_query(index_name, query)
        written = 0
        with open(path, "w", encoding="utf-8") as handle:
            while written < total:
                response = self.engine._search_with_shard_check(
                    index_name,
                    {"query": query, "from": written, "size": 500, "_source": {"excludes": ["*embedding*", "indexes.embedding"]}, "sort": ["_doc"]},
                )
                hits = response.get("hits", {}).get("hits", []) or []
                if not hits:
                    break
                for hit in hits:
                    handle.write(json.dumps(dict(hit.get("_source") or {}, _id=hit.get("_id")), ensure_ascii=False) + "\n")
                written += len(hits)
        return path

    def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """Expose the old ID lookup method."""
        return self.engine.get(data_id)
