"""KnowledgeService —— 文本级 CRUD 层。

职责：接收文本字段的文档/查询，生成向量与 _id、处理时间字段、补齐 `process_one_data` 中
**不依赖外部 HTTP/LLM** 的业务默认，委托 `KnowledgeRepository`。
注入 `EmbeddingClient`（低耦合：embedding 可替换、可测试）。

**仍然刻意排除**（属重业务逻辑，留给后续 pipeline / 独立模块，不在 CRUD 内）：
- 去重 dedup（find_duplicates / SimilityTools / Dify LLM）+ is_update_data 软删除
- 类目映射 primary_category 构造（依赖 category_service HTTP，仅做 category_id→str 归一）

**已在本层补齐**（与旧 `process_one_data` 行为对齐，纯本地、零外部 IO）：
- is_audit→audit_result 迁移；audit_result/quality_level/from_type 缺省与合法性矫正
- from_type_norm（基于规则映射 `legacy_get_from_norm_type`）
- keywords（基于 jieba.analyse 的 `legacy_gen_keyword_by_title_content`，无外部 LLM 调用）
- tags 缺省 = keywords
- dataset 缺省 = index_name
- category_infos[].category_id → str
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
from typing import Any, Dict, List, Optional, Tuple, Union

from kdb.config.loader import load_config
from kdb.crud.ids import gen_data_id
from kdb.crud.models import SCHEMA_FIELDS
from kdb.crud.repository import KnowledgeRepository
from kdb.embedding.client import EmbeddingClient, build_embedding_client
from kdb.legacy_bridge import (
    cosine_similarity,
    legacy_gen_keyword_by_title_content,
    legacy_get_from_norm_type,
)

VALID_AUDIT_RESULTS = {-1, 0, 1}
VALID_QUALITY_LEVELS = {"high", "mid", "low"}
MULTIMODAL_FILE_TYPES = {"image", "video", "audio", "file"}
MULTIMODAL_PREFIX_PLACEHOLDER = "[multimodal_prefix]"

logger = logging.getLogger(__name__)


class KnowledgeService:
    """文本级知识库读写接口。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        default_index: Optional[str] = None,
        multimodal_prefix: str = "",
    ) -> None:
        """
        Args:
            repository: 纯向量 CRUD 仓库。
            embedding_client: 向量生成客户端（注入）。
            default_index: 默认索引名。
            multimodal_prefix: search_text 返回时把 `[multimodal_prefix]` 替换成该字符串
                （与旧 `SearchDataInterface.multimodal_prefix` 一致）；空串表示不替换。
        """
        self._repo = repository
        self._embedding = embedding_client
        self._default_index = default_index or repository._default_index
        self._multimodal_prefix = multimodal_prefix or ""

    @classmethod
    def from_config(cls, config_path: str, index_name: Optional[str] = None) -> "KnowledgeService":
        """从 rebuild config（config_test.json）构造完整 Service。

        若 cfg 中含 `legacy_search_config_path` 指向旧 `config_for_search_index.json`，则从中
        读取 `multimodal_prefix` 自动注入，保证 search 返回与旧 `search_data_by_query` 一致。
        """
        cfg = load_config(config_path)
        index_name = index_name or cfg.get("test_index_name")
        repo = KnowledgeRepository(
            engine_config_path=cfg["engine_config_path"], default_index=index_name
        )
        embedding = build_embedding_client(cfg["embedding_config_path"])
        multimodal_prefix = cls._read_multimodal_prefix(cfg)
        return cls(
            repo,
            embedding,
            default_index=index_name,
            multimodal_prefix=multimodal_prefix,
        )

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
            # 与旧 `search_data_by_query` 一致：返回前把 [multimodal_prefix] 替换为配置前缀。
            # 当构造时未注入 prefix（空串）时该 replace 是 no-op，等价于保留占位符。
            content = doc.get("content")
            if isinstance(content, str) and MULTIMODAL_PREFIX_PLACEHOLDER in content:
                doc["content"] = content.replace(
                    MULTIMODAL_PREFIX_PLACEHOLDER, self._multimodal_prefix
                )
        return candidate_docs, total_num

    def get(self, data_id: str, index_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按 _id 取文档（透传仓库 get）。"""
        return self._repo.get(data_id, index_name=index_name)

    # ================= 内部：向量化 + 业务默认 =================
    def _prepare_document(
        self, data: Dict[str, Any], index_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """生成向量 + _id + 时间字段 + 业务默认（逐行对齐旧 `process_one_data`）。

        本层补齐的业务默认严格对应旧 process_one_data 中**不依赖外部 HTTP/LLM** 的部分：
        is_audit→audit_result、audit_result/quality_level/from_type 缺省与矫正、
        from_type_norm、keywords（jieba 本地）、tags、dataset、category_infos[].category_id→str、
        multimodal_contents→content 拼接。primary_category 构造依赖外部 HTTP，留给 pipeline。

        刻意保留与旧实现完全一致的 `_id` 守卫语义：业务默认仅在新建文档（`_id` 未提供）时
        填入，更新场景（调用方传入 `_id`）一律不动。这是为了与旧 process_one_data 的写入
        路径行为对齐。
        """
        is_new = "_id" not in data

        # 1. 非 schema 字段归集进 ext_info（与旧实现完全一致）
        ext_info = data.get("ext_info", {})
        for field in list(data.keys()):
            if field not in SCHEMA_FIELDS:
                ext_info[field] = data.pop(field)
        data["ext_info"] = ext_info

        # 2. is_audit → audit_result；audit_result/quality_level 缺省与合法性矫正（仅新建）
        if "is_audit" in data:
            data["audit_result"] = data.pop("is_audit")
        if is_new:
            if "audit_result" not in data:
                data["audit_result"] = -1
            elif data.get("audit_result") and data["audit_result"] not in VALID_AUDIT_RESULTS:
                logger.warning(
                    "audit_result 非法 %r，重置为 -1", data["audit_result"]
                )
                data["audit_result"] = -1
            if "quality_level" not in data:
                data["quality_level"] = "mid"
            elif data.get("quality_level") not in VALID_QUALITY_LEVELS:
                logger.warning(
                    "quality_level 非法 %r，重置为 mid", data["quality_level"]
                )
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
                    keywords = [w["word"] for w in raw if isinstance(w, dict) and "word" in w]
                    if keywords:
                        data["keywords"] = keywords
                except Exception as exc:  # pragma: no cover
                    logger.warning("生成 keywords 失败: %s", exc)

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

        # 11. from_type / from_type_norm / tags（仅新建）
        if is_new:
            if "from_type" not in data:
                data["from_type"] = "unknown"
            elif not isinstance(data["from_type"], str):
                data["from_type"] = str(data["from_type"])
            if "from_type_norm" not in data and legacy_get_from_norm_type is not None:
                try:
                    data["from_type_norm"] = legacy_get_from_norm_type(data)
                except Exception as exc:  # pragma: no cover
                    logger.warning("生成 from_type_norm 失败: %s", exc)
            if "tags" not in data:
                data["tags"] = data.get("keywords", [])

        # 12. del_flag=0：底层引擎的存储契约（不是业务默认值）：
        #     旧 EsSearchInterface 的 search_multi/search/search_by_page 在未显式指定 del_flag
        #     时会强制注入 {term: del_flag=0} 过滤；缺该字段的文档**默认搜不到**。
        if "del_flag" not in data and is_new:
            data["del_flag"] = 0

        # 13. category_infos[].category_id 强制为 str（与旧实现一致；primary_category 构造跳过）
        if data.get("category_infos"):
            for category_info in data["category_infos"]:
                if "category_id" in category_info:
                    category_info["category_id"] = str(category_info["category_id"])

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
                if piece:
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

    def _regenerate_embeddings(self, data: Dict[str, Any]) -> None:
        """更新时按需重算向量（仅对传入的 title/content/indexes 生效）。"""
        if "title" in data:
            data.pop("title_embedding", None)
            if data.get("title"):
                data["title_embedding"] = self._embedding.text2embedding(data["title"]).tolist()
        if "content" in data:
            data.pop("content_embedding", None)
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
