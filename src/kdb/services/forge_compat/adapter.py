"""Translate the earlier forge protocol onto the single published application.

This module has no retrieval, deduplication, indexing or scoring algorithm.
The earlier forge update payload contract is retained here; all database
operations delegate to the single published engine.
"""
import copy
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from kdb.services.forge_compat.repository import KnowledgeRepository
from kdb.embedding.client import EmbeddingClient, build_embedding_client
from kdb.config.loader import load_config
from kdb.counting import build_from_type_count_query, validate_count_index
from kdb.services.forge_compat.schemas import SCHEMA_FIELDS


logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: Optional[EmbeddingClient],
        default_index: Optional[str] = None,
        multimodal_prefix: str = "",
        check_duplicate: Optional[Union[bool, Mapping[str, Any]]] = None,
        is_need_llm: Optional[bool] = None,
        simility_tools: Any = None,
        category_client: Any = None,
        *,
        legacy_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        # Preserve both historical fifth-position contracts before creating state.
        if isinstance(check_duplicate, Mapping):
            if legacy_config is not None:
                raise TypeError("legacy_config supplied both positionally and by keyword")
            legacy_config = dict(check_duplicate)
            check_duplicate = None
        self._repo = repository
        self._embedding = embedding_client
        self._default_index = default_index or repository._default_index
        self._multimodal_prefix = multimodal_prefix or ""
        self._init_legacy_compat(legacy_config)
        if check_duplicate is not None:
            self.check_duplicate = check_duplicate
        if is_need_llm is not None:
            self.is_need_llm = is_need_llm
        self.simility_tools = simility_tools
        self._category = category_client if category_client is not None else self
        self._bind_category_protocol()

    def _init_legacy_compat(self, legacy_config: Optional[Mapping[str, Any]] = None) -> None:
        """Initialise attributes expected by old callers."""
        from kdb.retrieval.application.search_index_data_interface import SearchDataInterface

        self._interface = SearchDataInterface.__new__(SearchDataInterface)
        config = dict(legacy_config or {})
        self._legacy_config = config
        self.engine = getattr(self._repo, "_engine", self._repo)
        self.embedding_tools = self._embedding
        self.multimodal_prefix = self._multimodal_prefix
        self.is_need_llm = bool(config.get("is_need_llm", False))
        self.check_duplicate = bool(config.get("check_duplicate", True))
        self.category_service_url = config.get("category_service_url", "") or ""
        self.category_update_time_interval = config.get("category_update_time_interval", 36000)
        self.category_update_time_dict: Dict[str, float] = {}
        self.all_client_category_dict: Dict[str, Dict[str, Any]] = {}
        self.doc_schema_field = set(SCHEMA_FIELDS)
        self.simility_tools = None

    @classmethod
    def _from_interface(cls, interface, default_index=None, *, legacy_config=None):
        """Bind an already initialized canonical object without reinitializing it."""
        self = cls.__new__(cls)
        self._interface = interface
        self._repo = KnowledgeRepository(engine=interface.engine, default_index=default_index)
        self._embedding = getattr(interface, "embedding_tools", None)
        self._default_index = default_index or self._repo._default_index
        self._multimodal_prefix = getattr(interface, "multimodal_prefix", "") or ""
        self._legacy_config = dict(legacy_config or {})
        self._category = self
        self._bind_category_protocol()
        return self

    def _bind_category_protocol(self):
        canonical_map = self._interface.map_cate_name_to_id

        def map_category(client, name):
            category = self._category
            if category is self:
                return canonical_map(client, name)
            return category.map_cate_name_to_id(client, name)

        self._interface.map_cate_name_to_id = map_category

    @classmethod
    def from_config(cls, config_path: str, index_name: Optional[str] = None) -> "KnowledgeService":
        """从 rebuild config（config_test.json）构造完整 Service。

        若 cfg 中含 `legacy_search_config_path` 指向旧 `config_for_search_index.json`，则从中
        读取 `multimodal_prefix` 自动注入，保证 search 返回与旧 `search_data_by_query` 一致。
        """
        cfg = load_config(config_path)
        index_name = index_name or cfg.get("default_index_name")
        if not index_name:
            index_name = cfg.get("test_index_name")
            logger.warning(
                "未指定 default_index_name；回退到 %s，请确认生产索引配置",
                f"test_index_name={index_name}" if index_name else "engine 默认索引",
            )
        legacy_cfg = cls._load_legacy_search_cfg(cfg)
        repo = KnowledgeRepository(
            engine_config_path=cfg["engine_config_path"], default_index=index_name
        )
        embedding = build_embedding_client(cfg["embedding_config_path"])
        multimodal_prefix = legacy_cfg.get("multimodal_prefix", "") or ""
        if not multimodal_prefix:
            logger.warning("multimodal_prefix 未配置；检索时占位符将被替换为空串")
        return cls(
            repo,
            embedding,
            default_index=index_name,
            multimodal_prefix=multimodal_prefix,
            legacy_config=legacy_cfg,
        )

    @classmethod
    def from_count_config(cls, config_path: str) -> "KnowledgeService":
        """Build a count-only service with no ensure, embedding or legacy config I/O."""
        from kdb.es.engine import RoutedLegacyEngine

        cfg = load_config(config_path)
        default_index = cfg.get("default_index_name") or cfg.get("test_index_name")
        engine = RoutedLegacyEngine(
            config_path=cfg["engine_config_path"],
            index_name=default_index,
            ensure_index=False,
            extra_params={"ensure_index_on_init": False},
        )
        repository = KnowledgeRepository(engine=engine, default_index=default_index)
        return cls(repository, None, default_index=default_index)

    def __getattr__(self, name):
        interface = self.__dict__.get("_interface")
        if interface is None:
            raise AttributeError(name)
        return getattr(interface, name)

    def __setattr__(self, name, value):
        interface = self.__dict__.get("_interface")
        if not name.startswith("_") and interface is not None and not hasattr(type(self), name):
            setattr(interface, name, value)
        else:
            object.__setattr__(self, name, value)

    def _search_index_names(self, index_name):
        value = index_name if index_name else self._repo._default_index
        return self._join_index_names(value)

    @staticmethod
    def _join_index_names(value):
        return ",".join(value) if isinstance(value, (list, tuple)) else value

    def search_text(
        self,
        query: str,
        index_name: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._interface.search_data_by_query(
            query, index_names=self._search_index_names(index_name),
            condition_dicts=condition_dicts, size=size, search_type=search_type,
            data_type=data_type, use_synonyms=use_synonyms,
        )

    def search_text_multi(
        self, query_list: List[str], index_name=None, condition_dicts=None,
        size: int = 10, search_type: str = "qa", data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._interface.search_data_by_multi_query(
            query_list, index_names=self._search_index_names(index_name),
            condition_dicts=condition_dicts, size=size, search_type=search_type,
            data_type=data_type, use_synonyms=use_synonyms,
        )

    def web_search(
        self, query: str, client=None, index_name=None, condition_dicts=None,
        page_size=None, page_num: int = 1, score_threshold=None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self._interface.web_search_data(
            query, client=client, index_names=self._join_index_names(index_name or None),
            condition_dicts=condition_dicts, page_size=page_size, page_num=page_num,
            score_threshold=score_threshold,
        )

    def search_data_by_query(
        self, query: str, index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None, size: int = 10,
        search_type: str = "qa", data_type: str = "text", use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self.search_text(query, index_names, condition_dicts, size, search_type, data_type, use_synonyms)

    def search_data_by_multi_query(
        self, query_list: List[str], index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None, size: int = 10,
        search_type: str = "qa", data_type: str = "text", use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self.search_text_multi(query_list, index_names, condition_dicts, size, search_type, data_type, use_synonyms)

    def web_search_data(
        self, query: str, client: str = None, index_names: str = None,
        condition_dicts: List[Dict[str, Any]] = None, page_size: int = None,
        page_num: int = 1, score_threshold: float = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        return self.web_search(query, client, index_names, condition_dicts, page_size, page_num, score_threshold)

    def insert_data(self, data, **kwargs):
        # Earlier forge HTTP routes did not mutate the caller's document dict.
        return self._interface.insert_data(copy.deepcopy(data), **kwargs)

    def insert_text(self, data, index_name=None, **kwargs):
        return self.insert_data(data, index_name=index_name or self._default_index, **kwargs)

    def batch_insert(self, data_list, **kwargs):
        return self._interface.batch_insert_data(data_list, **kwargs)

    def get(self, document_id, index_name=None):
        return self._interface.engine.get(document_id, index_names=index_name or self._default_index)

    def delete(self, document_id, index_name=None, refresh=False):
        return self._interface.delete_data(
            document_id, index_names=index_name or self._default_index, refresh=refresh
        )

    def update(
        self,
        data_id: str,
        doc: Dict[str, Any],
        index_name: Optional[str] = None,
        regenerate_embedding: bool = False,
        refresh: bool = False,
    ) -> bool:
        """按 _id 局部更新文本字段；可选重算向量。总是刷新 update_time。

        refresh=True 时强制刷新索引以保证更新立即可见（serverless 上 get-by-id
        非严格实时；测试与对齐场景必须传 True）。
        """
        payload = copy.deepcopy(doc)
        payload.pop("_id", None)  # _id 通过参数传，不放进 doc 体
        if regenerate_embedding:
            if "indexes" not in payload and ("title" in payload or "synonyms_title" in payload):
                existing = self._repo.get(data_id, index_name=index_name)
                if existing is None:
                    raise ValueError("Cannot rebuild retrieval indexes without the stored document")
                self._sync_retrieval_indexes(payload, existing)
            self._regenerate_embeddings(payload)
        payload["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self._repo.update_by_id(data_id, payload, index_name=index_name, refresh=refresh)

    @staticmethod
    def _sync_retrieval_indexes(data: Dict[str, Any], existing: Dict[str, Any]) -> None:
        """同步修改后的检索文本，同时保留自定义和图片检索项。"""
        previous = [existing.get("title"), *(existing.get("synonyms_title") or [])]
        current = [
            data.get("title", existing.get("title")),
            *(data.get("synonyms_title", existing.get("synonyms_title")) or []),
        ]
        current = [text for text in current if isinstance(text, str) and text.strip()]
        retained = set(current)
        retained.update(
            item["text"] for item in existing.get("image_indexes", [])
            if isinstance(item.get("text"), str)
        )
        obsolete = {text for text in previous if isinstance(text, str)} - retained
        indexes = [
            copy.deepcopy(item) for item in existing.get("indexes", [])
            if item.get("text") not in obsolete
        ]
        for text in current:
            if not any(item.get("text") == text for item in indexes):
                indexes.append({"text": text})
        data["indexes"] = indexes

    def _regenerate_embeddings(self, data: Dict[str, Any]) -> None:
        """更新时按需重算向量（仅对传入的 title/content/indexes 生效）。"""
        if "title" in data:
            data["title_embedding"] = None
            if data.get("title"):
                data["title_embedding"] = self._embedding.text2embedding(data["title"]).tolist()
        if "content" in data:
            data["content_embedding"] = None
            if data.get("content"):
                data["content_embedding"] = self._embedding.text2embedding(
                    data["content"]
                ).tolist()
        for idx in data.get("indexes", []):
            if "text" in idx:
                idx["embedding"] = self._embedding.text2embedding(idx["text"]).tolist()

    def get_from_type_count(
        self,
        index_name: Optional[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        from_type: str = "chat_auto",
    ) -> Tuple[bool, int, str]:
        """Return an exact count for high-quality records of the requested source."""
        try:
            validate_count_index(index_name)
            query = build_from_type_count_query(from_type, start, end)
            if index_name is None or index_name == "":
                return True, 0, ""
            count = self._repo.count_by_query(index_name, query)
            return True, count, ""
        except Exception as exc:
            # Exception messages/tracebacks can contain provider URLs or credentials.
            logger.warning("source-type count failed: error_type=%s", type(exc).__name__)
            return False, 0, "统计失败"

    @staticmethod
    def _load_legacy_search_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Read the optional legacy service config without hiding missing configuration."""
        path = cfg.get("legacy_search_config_path") or cfg.get("search_config_path")
        if not path or not os.path.exists(path):
            logger.warning("旧 search 配置缺失，使用内置缺省: %r", path)
            return {}
        try:
            return load_config(path)
        except Exception as exc:
            logger.warning("读取旧 search 配置失败: %s", exc)
            return {}


from kdb.retrieval.application.search_index_data_interface import SearchDataInterface
