"""KnowledgeService —— 文本级 CRUD 层。

职责：接收文本字段的文档/查询，生成向量与 _id、处理时间字段、补齐旧服务业务副作用，委托
`KnowledgeRepository`。
注入 `EmbeddingClient`（低耦合：embedding 可替换、可测试）。

**已在本层补齐**（与旧 `SearchDataInterface` 行为对齐）：
- is_audit→audit_result 迁移；audit_result/quality_level/from_type 缺省与合法性矫正
- from_type_norm（基于规则映射 `legacy_get_from_norm_type`）
- keywords（基于 jieba.analyse 的 `legacy_gen_keyword_by_title_content`，无外部 LLM 调用）
- tags 缺省 = keywords
- dataset 缺省 = index_name
- category_infos[].category_id → str
- 显式类目的 primary_category 构造和默认分组；不包含挖掘侧的 Payoneer Olive 推断
- find_duplicates / SimilityTools 查重及 insert_data 的重复软删除
- multimodal_contents → content 拼接（使用字面 `[multimodal_prefix]` 占位，与旧实现一致）
- search_text 返回前把 content 中 `[multimodal_prefix]` 替换为构造时注入的实际前缀

**del_flag 例外**：`del_flag=0` 不算业务默认值，而是底层 ES 引擎的**存储契约**——旧
`EsSearchInterface.search_multi/search/search_by_page` 在未显式指定 del_flag 时会强制
注入 `{term: del_flag=0}`，缺该字段的文档默认不可见。CRUD 必须在新建时填 0 才能保证
插入即可检索，与旧 `process_one_data` 一致。

向量化、业务默认与相似度逐行复刻旧实现（search_index_data_interface.py 的 process_one_data /
search_data_by_query / _cal_similarity），保证与旧实现行为对齐。
"""

import copy
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
from urllib.parse import quote

from kdb.config.loader import load_config
from kdb.crud.ids import gen_data_id
from kdb.crud.legacy_compat import LegacySearchDataInterfaceMixin
from kdb.crud.models import SCHEMA_FIELDS
from kdb.crud.repository import KnowledgeRepository
from kdb.embedding.client import EmbeddingClient, build_embedding_client
from kdb.legacy_bridge import (
    LegacySimilityTools,
    cosine_similarity,
    legacy_gen_keyword_by_title_content,
    legacy_get_from_norm_type,
)

VALID_AUDIT_RESULTS = {-1, 0, 1, 2}
VALID_QUALITY_LEVELS = {"high", "mid", "low"}
MULTIMODAL_FILE_TYPES = {"image", "video", "audio", "file"}
MULTIMODAL_PREFIX_PLACEHOLDER = "[multimodal_prefix]"

logger = logging.getLogger(__name__)


class _FallbackSimilityTools:
    """Local legacy thresholds when the optional similarity dependency is absent."""

    def is_simility_knowledge(
        self, doc_1, doc_2, is_need_llm=False, is_only_title=False,
        basic_threshold=0.7, title_basic_threshold=0.95,
    ) -> int:
        if doc_1.get("data_type") != doc_2.get("data_type") or doc_1.get("platform") != doc_2.get("platform"):
            return 0
        scores = []
        for field in ("title_embedding", "content_embedding"):
            if field in doc_1 and field in doc_2:
                scores.append(cosine_similarity(doc_1[field], doc_2[field]))
            elif field not in doc_1 and field not in doc_2:
                scores.append(-1)
            else:
                return 0
        if max(scores) < basic_threshold:
            return 0
        if is_only_title and scores[0] > title_basic_threshold:
            return 1
        if min(scores) > title_basic_threshold:
            return 1
        if is_need_llm:
            raise RuntimeError("LLM 判重不可用：请配置或注入带 LLM 能力的 SimilityTools")
        return 0


class KnowledgeService(LegacySearchDataInterfaceMixin):
    """文本级知识库读写接口。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        default_index: Optional[str] = None,
        multimodal_prefix: str = "",
        check_duplicate: Optional[Union[bool, Mapping[str, Any]]] = None,
        is_need_llm: Optional[bool] = None,
        simility_tools: Any = None,
        category_client: Any = None,
        *,
        legacy_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Args:
            repository: 纯向量 CRUD 仓库。
            embedding_client: 向量生成客户端（注入）。
            default_index: 默认索引名。
            multimodal_prefix: search_text 返回时把 `[multimodal_prefix]` 替换成该字符串
                （与旧 `SearchDataInterface.multimodal_prefix` 一致）；空串会删除占位符。
            check_duplicate/is_need_llm: 显式值覆盖旧配置，None 使用配置缺省。
            simility_tools: 注入查重工具，否则在查重时懒加载。
            category_client: 可选 map_cate_name_to_id 协议实例，用于 web 类目过滤。
            legacy_config: 旧 search 业务配置；也兼容作为第五个位置参数传入。
        """
        # The two merge parents used the fifth position for different arguments.
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

    def _get_simility_tools(self) -> Any:
        """Use injected/configured duplicate checking, falling back to local thresholds."""
        if self.simility_tools is None:
            if LegacySimilityTools is not None:
                path = self._legacy_config.get("simility_config_path")
                try:
                    self.simility_tools = LegacySimilityTools(path or None)
                except Exception as exc:
                    logger.warning("加载 SimilityTools 失败，使用本地阈值判重: %s", exc)
            if self.simility_tools is None:
                self.simility_tools = _FallbackSimilityTools()
        return self.simility_tools

    batch_insert = LegacySearchDataInterfaceMixin.batch_insert_data

    @staticmethod
    def _read_multimodal_prefix(cfg: Dict[str, Any]) -> str:
        """从 cfg 引用的旧 search config 中读 multimodal_prefix（缺失则返回空串）。"""
        search_cfg_path = cfg.get("legacy_search_config_path") or cfg.get("search_config_path")
        if not search_cfg_path or not os.path.exists(search_cfg_path):
            return ""
        try:
            with open(search_cfg_path, "r", encoding="utf-8") as f:
                search_cfg = json.load(f)
            return search_cfg.get("multimodal_prefix", "") or ""
        except Exception as exc:  # pragma: no cover
            logger.warning("读取 legacy_search_config_path 失败: %s", exc)
            return ""

    # ================= 写 =================
    def insert_text(
        self,
        doc: Dict[str, Any],
        index_name: Optional[str] = None,
        refresh_imm: bool = False,
    ) -> Tuple[bool, str]:
        """插入一条文本文档（自动生成向量与 _id），返回 (是否成功, 消息)。

        index_name 也参与 `_prepare_document`：缺 `dataset` 时用 index_name 兜底，
        与旧 `process_one_data(data, index_name=...)` 行为一致。
        """
        target_index = index_name or self._default_index
        prepared = self._prepare_document(copy.deepcopy(doc), index_name=target_index)
        ok = self._repo.insert(prepared, index_name=index_name, refresh_imm=refresh_imm)
        return (True, "") if ok else (False, "insert failed")

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

    def delete(
        self,
        data_id: str,
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> bool:
        """按 _id 删除。"""
        return self._repo.delete(data_id, index_name=index_name, refresh=refresh)

    # ================= 读 =================
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
        """文本检索：embed query → 混合检索 → 逐 doc 计算 similarity（与旧 search_data_by_query 一致）。

        返回 (candidate_docs, total_num)；候选数为 size*2，**不截断不排序**（与旧实现一致，
        排序/截断交给调用方）。每个 doc 带 `similarity` 字段。
        """
        query_embedding = self._embedding.text2embedding(query)
        search_query: Dict[str, Any] = {
            "query": query,
            "vector": {"value": query_embedding},
        }

        # 索引名：旧实现对 str 按逗号切分；falsy 时传 None（仓库回退默认索引）
        idx_arg: Optional[Union[str, List[str]]] = None
        if index_name:
            idx_arg = index_name.split(",") if isinstance(index_name, str) else index_name

        # 默认检索条件（复刻旧 search_data_by_query）
        if not condition_dicts:
            condition_dicts = []
            condition_dicts.append({"quality_level": ["high"], "data_type": ["qa"]})
            condition_dicts.append({"audit_result": [1, 2], "data_type": ["qa"]})
        for condition_dict in condition_dicts:
            if "audit_result" not in condition_dict:
                condition_dict["audit_result"] = [1, 2, -1]
        search_query["attribute"] = condition_dicts

        candidate_docs, total_num = self._repo.search_multi(
            search_query, index_name=idx_arg, size=size * 2
        )
        for doc in candidate_docs:
            doc["similarity"] = self._cal_similarity(
                query,
                query_embedding,
                doc,
                search_type=search_type,
                data_type=data_type,
                use_synonyms=use_synonyms,
            )
            # 与旧 `search_data_by_query` 一致：内部文件地址附带 fileName，外链不改。
            self.render_multimodal_urls(doc)
        return candidate_docs, total_num

    def search_text_multi(
        self, query_list: List[str], index_name=None, condition_dicts=None,
        size: int = 10, search_type: str = "qa", data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Remote public name backed by the same routed multi-query implementation."""
        return self.search_data_by_multi_query(
            query_list, index_name, condition_dicts, size, search_type, data_type, use_synonyms
        )

    def _search_text_multi_threading(
        self, query_list: List[str], index_name=None, condition_dicts=None,
        size: int = 10, search_type: str = "qa", data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Retain the remote fallback entry point without a second search algorithm."""
        return self._search_data_by_multi_query_threading(
            query_list, index_name, condition_dicts, size, search_type, data_type, use_synonyms
        )

    def web_search(
        self, query: str, client=None, index_name=None, condition_dicts=None,
        page_size=None, page_num: int = 1, score_threshold=None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Remote public name backed by the generic category/pagination implementation."""
        return self.web_search_data(
            query, client, index_name, condition_dicts, page_size, page_num, score_threshold
        )

    def render_multimodal_urls(self, doc: Dict[str, Any]) -> None:
        """原地渲染检索结果中的多模态内部地址。

        只替换 `[multimodal_prefix]` + ``path`` 占位符；如果对应条目有 fileName，
        按旧服务规则追加 URL 编码后的 ``filename`` 参数。没有登记 fileName 的占位符
        仍只替换前缀，外部 URL 保持不变。
        """
        if not doc:
            return
        content = doc.get("content")
        if not isinstance(content, str) or MULTIMODAL_PREFIX_PLACEHOLDER not in content:
            return

        path_name_pairs = []
        for file_info in doc.get("multimodal_contents") or []:
            if not isinstance(file_info, dict):
                continue
            path = file_info.get("path")
            file_name = file_info.get("fileName")
            if path and file_name:
                path_name_pairs.append((path, file_name))
        path_name_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)

        for path, file_name in path_name_pairs:
            placeholder = f"{MULTIMODAL_PREFIX_PLACEHOLDER}{path}"
            if placeholder not in content:
                continue
            separator = "&" if "?" in path else "?"
            full_url = (
                f"{self._multimodal_prefix}{path}{separator}"
                f"filename={quote(str(file_name), safe='')}"
            )
            content = content.replace(placeholder, full_url)
        doc["content"] = content.replace(
            MULTIMODAL_PREFIX_PLACEHOLDER, self._multimodal_prefix
        )

    def get(self, data_id: str, index_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按 _id 取文档（透传仓库 get）。"""
        return self._repo.get(data_id, index_name=index_name)

    # ================= 内部：向量化 + 业务默认 =================
    def _prepare_document(
        self, data: Dict[str, Any], index_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成向量 + _id + 时间字段 + 业务默认（逐行对齐旧 `process_one_data`）。

        本层补齐旧 process_one_data 的通用 CRUD 默认：
        is_audit→audit_result、audit_result/quality_level/from_type 缺省与矫正、
        from_type_norm、keywords（jieba 本地）、tags、dataset、category_infos[].category_id→str、
        multimodal_contents→content 拼接、显式 primary_category/默认类目构造。

        刻意保留与旧实现完全一致的 `_id` 守卫语义：业务默认仅在新建文档（`_id` 未提供）时
        填入；非法 audit_result 和非字符串 from_type 在更新时也会规范化。
        """
        is_new = "_id" not in data

        # 1. 非 schema 字段归集进 ext_info（与旧实现完全一致）
        ext_info = data.get("ext_info", {})
        for field in list(data.keys()):
            if field not in SCHEMA_FIELDS:
                ext_info[field] = data.pop(field)
        data["ext_info"] = ext_info

        # 2. 缺省仅用于新建；truthy 非法 audit_result 在 upsert 时也需要矫正。
        if "is_audit" in data:
            data["audit_result"] = data.pop("is_audit")
        if "audit_result" not in data and is_new:
            data["audit_result"] = -1
        if data.get("audit_result") and data["audit_result"] not in VALID_AUDIT_RESULTS:
            logger.warning("audit_result 非法 %r，重置为 -1", data["audit_result"])
            data["audit_result"] = -1
        if "quality_level" not in data and is_new:
            data["quality_level"] = "mid"
        elif is_new and data.get("quality_level") not in VALID_QUALITY_LEVELS:
            logger.warning("quality_level 非法 %r，重置为 mid", data["quality_level"])
            data["quality_level"] = "mid"

        # 3. indexes / image_indexes 初始化与冗余构造
        if "indexes" not in data:
            data["indexes"] = []
        if "image_indexes" not in data:
            data["image_indexes"] = []

        for idx in data.get("image_indexes", []):
            if "text" in idx:
                data["indexes"].append({"text": idx["text"]})

        if data.get("title") and not any(
            idx.get("text") == data["title"] for idx in data.get("indexes", [])
        ):
            data["indexes"].append({"text": data["title"]})

        if data.get("synonyms_title"):
            if not isinstance(data["synonyms_title"], list):
                logger.warning("synonyms_title 不是列表格式，将被忽略")
                data["synonyms_title"] = []
            else:
                for syn_title in data["synonyms_title"]:
                    if not isinstance(syn_title, str):
                        continue
                    if not any(idx.get("text") == syn_title for idx in data["indexes"]):
                        data["indexes"].append({"text": syn_title})

        # 4. indexes / image_indexes 向量化
        # 旧 process_one_data 会先丢弃空文本，避免把空字符串送入 embedding 服务。
        data["indexes"] = [
            idx for idx in data["indexes"]
            if not ("text" in idx and not str(idx.get("text") or "").strip())
        ]
        data["image_indexes"] = [
            idx for idx in data["image_indexes"]
            if not ("text" in idx and not str(idx.get("text") or "").strip())
        ]
        for idx in data["indexes"]:
            if "text" in idx and "embedding" not in idx:
                embedding = self._embedding.text2embedding(idx["text"])
                if embedding is not None:
                    idx["embedding"] = embedding.tolist()
        for idx in data["image_indexes"]:
            if "text" in idx and "embedding" not in idx:
                embedding = self._embedding.text2embedding(idx["text"])
                if embedding is not None:
                    idx["embedding"] = embedding.tolist()

        # 5. multimodal_contents → content 拼接（必须在 title/content 向量化之前）
        if data.get("multimodal_contents"):
            data["content"] = self._join_multimodal_contents(data["multimodal_contents"])

        # 6. title / content 向量
        if data.get("title") and "title_embedding" not in data:
            title_embedding = self._embedding.text2embedding(data["title"])
            if title_embedding is not None:
                data["title_embedding"] = title_embedding.tolist()
        if data.get("content") and "content_embedding" not in data:
            content_embedding = self._embedding.text2embedding(data["content"])
            if content_embedding is not None:
                data["content_embedding"] = content_embedding.tolist()

        # 7. keywords（jieba.analyse.textrank，无外部 LLM）；缺失时基于 title+content 生成
        if not data.get("keywords") and (data.get("title") or data.get("content")):
            if legacy_gen_keyword_by_title_content is not None:
                try:
                    raw = legacy_gen_keyword_by_title_content(
                        data.get("title", ""), data.get("content", ""), topK=5
                    )
                    keywords = [w["word"] for w in raw]
                    if keywords:
                        data["keywords"] = keywords
                except ImportError:
                    logger.warning("关键词生成工具未实现，跳过关键词生成")

        # 8. 空 indexes 清理（旧实现：不允许更新时清空，故空则删字段）
        if "indexes" in data and not data.get("indexes"):
            del data["indexes"]
        if "image_indexes" in data and not data.get("image_indexes"):
            del data["image_indexes"]

        # 9. segment 不保留 title
        if data.get("data_type") == "segment":
            data.pop("title", None)
            data.pop("synonyms_title", None)

        # 10. 时间字段
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if "insert_time" not in data and is_new:
            data["insert_time"] = current_time
        elif "insert_time" in data and not isinstance(data["insert_time"], str):
            data["insert_time"] = current_time
        data["update_time"] = current_time

        # 11. from_type 转字符串不分新旧；其余缺省仍只补新建。
        if "from_type" not in data and is_new:
            data["from_type"] = "unknown"
        elif "from_type" in data and not isinstance(data["from_type"], str):
            data["from_type"] = str(data["from_type"])
        if is_new and "from_type_norm" not in data and legacy_get_from_norm_type is not None:
            data["from_type_norm"] = legacy_get_from_norm_type(data)
        if is_new and "tags" not in data:
            data["tags"] = data.get("keywords", [])

        # 12. del_flag=0：底层引擎的存储契约（不是业务默认值）：
        #     旧 EsSearchInterface 的 search_multi/search/search_by_page 在未显式指定 del_flag
        #     时会强制注入 {term: del_flag=0} 过滤；缺该字段的文档**默认搜不到**。
        if "del_flag" not in data and is_new:
            data["del_flag"] = 0

        # 13. 显式类目归一化、类目树解析和默认分组；不做挖掘推断。
        self._apply_category_defaults(data, is_new=is_new)

        # 14. dataset 缺省 = index_name（仅在 index_name 非空时）
        if not data.get("dataset") and index_name:
            data["dataset"] = index_name

        # 15. _id（复用旧 gen_data_id；segment 已去 title，与旧顺序一致）
        if "_id" not in data:
            data["_id"] = gen_data_id(data)

        return data

    def _join_multimodal_contents(self, multimodal_contents: List[Dict[str, Any]]) -> str:
        """拼接多模态内容；与旧 `SearchDataInterface.join_multimodal_contents` 等价。

        image/video/audio/file 类型的 path 以字面 `[multimodal_prefix]` 占位，等 search_text
        返回前再替换为构造时注入的真实前缀（与旧实现一致）。
        """
        content = ""
        for file_info in multimodal_contents:
            ftype = file_info.get("type")
            if ftype == "text":
                piece = file_info.get("content")
                content = f"{content}\n{piece}" if content else piece
            elif ftype in MULTIMODAL_FILE_TYPES:
                if file_info.get("path"):
                    address = f'{MULTIMODAL_PREFIX_PLACEHOLDER}{file_info["path"]}'
                else:
                    address = file_info.get("url")
                if not address:
                    continue
                content = f"{content}\n{address}" if content else address
        return content

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

    # ================= 内部：相似度（逐行复刻旧 _cal_similarity） =================
    def _cal_title_similarity(
        self,
        query: str,
        query_embedding,
        doc: Dict[str, Any],
        use_synonyms: bool = False,
    ) -> float:
        title_similarity = 0
        if doc.get("title") and doc.get("title_embedding"):
            title_similarity = cosine_similarity(query_embedding, doc["title_embedding"])
        if not use_synonyms:
            return title_similarity
        synonyms_titles = set(doc.get("synonyms_title", []))
        max_synonyms_similarity = 0
        for index_info in doc.get("indexes", []):
            text = index_info.get("text")
            if text and text in synonyms_titles and index_info.get("embedding"):
                synonyms_similarity = cosine_similarity(query_embedding, index_info["embedding"])
                max_synonyms_similarity = max(max_synonyms_similarity, synonyms_similarity)
        return max(title_similarity, max_synonyms_similarity)

    def _cal_similarity(
        self,
        query: str,
        query_embedding,
        doc: Dict[str, Any],
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> float:
        title_similarity = self._cal_title_similarity(query, query_embedding, doc, use_synonyms)
        if doc.get("content") and doc.get("content_embedding"):
            content_similarity = cosine_similarity(query_embedding, doc["content_embedding"])
        else:
            content_similarity = 0
        if search_type == "qa":
            if doc.get("title"):
                similarity = title_similarity + 0.2 * content_similarity
            else:
                similarity = content_similarity
        else:
            similarity = max(title_similarity, content_similarity)
        if "image" in data_type:
            image_similarity = 0
            if doc.get("image_indexes"):
                for image_index in doc["image_indexes"]:
                    if image_index.get("embedding"):
                        image_similarity = max(
                            image_similarity,
                            cosine_similarity(query_embedding, image_index["embedding"]),
                        )
            similarity = max(similarity, image_similarity)
        return similarity


class SearchDataInterface(KnowledgeService):
    """Drop-in constructor-compatible replacement for the old service class.

    The old public method names are inherited from ``KnowledgeService``'s
    compatibility mixin.  This constructor accepts the old
    ``SearchDataInterface(search_engine=None, config_path=None, **kwargs)``
    shape and converts a legacy single-provider ES config to the ES8.17
    routed configuration in memory.
    """

    def __init__(
        self,
        search_engine: Any = None,
        config_path: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        legacy_config: Dict[str, Any] = {}
        if config_path:
            legacy_config = load_config(config_path)
        index_name = kwargs.pop("index_name", None) or legacy_config.get("index_name")
        embedding_client = kwargs.pop("embedding_client", None)

        if search_engine is None:
            engine_config_path = legacy_config.get("search_engine_config_path") or legacy_config.get(
                "engine_config_path"
            )
            if not engine_config_path:
                raise ValueError("config_path 必须提供 search_engine_config_path/engine_config_path")
            search_engine = self.load_search_engine(
                engine_config_path, index_name=index_name, **kwargs
            )

        if embedding_client is None:
            embedding_config_path = legacy_config.get("embedding_config_path")
            if not embedding_config_path:
                raise ValueError("config_path 必须提供 embedding_config_path")
            embedding_client = build_embedding_client(embedding_config_path)

        default_index = index_name or getattr(search_engine, "index_name", None)
        repository = KnowledgeRepository(engine=search_engine, default_index=default_index)
        super().__init__(
            repository=repository,
            embedding_client=embedding_client,
            default_index=default_index,
            multimodal_prefix=legacy_config.get("multimodal_prefix", ""),
            legacy_config=legacy_config,
        )


__all__ = ["KnowledgeService", "SearchDataInterface"]
