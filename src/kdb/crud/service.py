"""KnowledgeService —— 文本级 CRUD 层，旧 `SearchDataInterface` 的完整替代。

职责：接收文本字段的文档/查询，生成向量与 _id、处理时间字段、补齐 `process_one_data` 的
业务默认，委托 `KnowledgeRepository`。注入 `EmbeddingClient`（低耦合：embedding 可替换、可测试）。

**接口分两组**：
- 新 API：`insert_text`（最小插入，**无查重**、异常上抛）/ `search_text` / `search_text_multi` /
  `web_search` / `update` / `delete` / `get` / `find_duplicates` / `batch_insert_data`。
- 旧接口完整替代：`insert_data`（默认查重 + is_update_data 软删覆盖 + 旧错误契约
  `(False,'数据处理失败'/'数据重复')`）以及 alias `search_data_by_query` /
  `search_data_by_multi_query` / `web_search_data` / `update_data` / `delete_data` /
  `search_data` / `get_data_by_id` / `update_data_value` / `get_unique_values`（旧参数名/顺序）。

**仍然刻意排除**（依赖外部 HTTP/LLM 的重业务，留给 pipeline）：
- `primary_category` 构造（依赖 category_service 的类目链查询；本层仅做
  category_infos[].category_id→str 归一 + web_search 的 category_names→ids 映射，经注入的
  `CategoryClient` 完成，未配置 URL 时安全降级）。
- 去重的 Dify LLM 判定分支（`is_need_llm=True` 且注入了带 LLM 配置的 SimilityTools 才生效；
  纯阈值判定为本地计算，已在本层可用）。

**del_flag 例外**：`del_flag=0` 不算业务默认值，而是底层 ES 引擎的**存储契约**——旧
`EsSearchInterface.search_multi/search/search_by_page` 在未显式指定 del_flag 时会强制
注入 `{term: del_flag=0}`，缺该字段的文档默认不可见。CRUD 必须在新建时填 0 才能保证
插入即可检索，与旧 `process_one_data` 一致。

向量化、业务默认、检索与相似度逐行复刻旧实现（search_index_data_interface.py 的
process_one_data / insert_data / find_duplicates / search_data_by_query /
search_data_by_multi_query / web_search_data / _cal_similarity）；与旧实现的**有意差异**
全部记录在 docs/CRUD_Legacy_Difference_Issues.md 并有离线测试契约锁定。
"""

import copy
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from kdb.category.client import CategoryClient
from kdb.config.loader import load_config
from kdb.crud.ids import gen_data_id
from kdb.crud.models import SCHEMA_FIELDS
from kdb.crud.repository import KnowledgeRepository
from kdb.embedding.client import EmbeddingClient, build_embedding_client
from kdb.legacy_bridge import (
    LegacySimilityTools,
    cosine_similarity,
    legacy_gen_keyword_by_title_content,
    legacy_get_from_norm_type,
)

VALID_AUDIT_RESULTS = {-1, 0, 1, 2}  # 与旧实现 si:476 的 [-1,0,1,2] 对齐；2=已审核态，检索契约 audit_result∈[1,2] 依赖它
VALID_QUALITY_LEVELS = {"high", "mid", "low"}
MULTIMODAL_FILE_TYPES = {"image", "video", "audio", "file"}
MULTIMODAL_PREFIX_PLACEHOLDER = "[multimodal_prefix]"

logger = logging.getLogger(__name__)


class _FallbackSimilityTools:
    """旧 `commons.simility_tools.SimilityTools` 的本地等价兜底（无 Dify LLM 能力）。

    仅在旧模块导入失败且未注入 simility_tools 时使用；阈值判定逻辑逐行复刻旧
    `SimilityTools.is_simility_knowledge`（simility_tools.py:69-106）。
    """

    def is_simility_knowledge(
        self,
        doc_1: Dict[str, Any],
        doc_2: Dict[str, Any],
        is_need_llm: bool = False,
        is_only_title: bool = False,
        basic_threshold: float = 0.7,
        title_basic_threshold: float = 0.95,
    ) -> int:
        if doc_1.get("data_type") != doc_2.get("data_type") or doc_1.get(
            "platform"
        ) != doc_2.get("platform"):
            return 0
        if "title_embedding" in doc_1 and "title_embedding" in doc_2:
            title_sim_score = cosine_similarity(
                doc_1["title_embedding"], doc_2["title_embedding"]
            )
        elif "title_embedding" not in doc_1 and "title_embedding" not in doc_2:
            title_sim_score = -1
        else:
            return 0
        if "content_embedding" in doc_1 and "content_embedding" in doc_2:
            content_sim_score = cosine_similarity(
                doc_1["content_embedding"], doc_2["content_embedding"]
            )
        elif "content_embedding" not in doc_1 and "content_embedding" not in doc_2:
            content_sim_score = -1
        else:
            return 0
        max_sim_score = max(title_sim_score, content_sim_score)
        min_sim_score = min(title_sim_score, content_sim_score)
        if max_sim_score < basic_threshold:
            return 0
        if is_only_title and title_sim_score > title_basic_threshold:
            return 1
        if min_sim_score > title_basic_threshold:
            return 1
        if is_need_llm:
            raise RuntimeError(
                "LLM 判重不可用：旧 commons.simility_tools 未导入且未注入 simility_tools"
            )
        return 0


class KnowledgeService:
    """文本级知识库读写接口。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        embedding_client: EmbeddingClient,
        default_index: Optional[str] = None,
        multimodal_prefix: str = "",
        check_duplicate: bool = True,
        is_need_llm: bool = False,
        simility_tools: Any = None,
        category_client: Optional[CategoryClient] = None,
    ) -> None:
        """
        Args:
            repository: 纯向量 CRUD 仓库。
            embedding_client: 向量生成客户端（注入）。
            default_index: 默认索引名。
            multimodal_prefix: search_text/web_search 返回时把 content 中的
                `[multimodal_prefix]` 占位符替换成该字符串（与旧
                `SearchDataInterface.multimodal_prefix` 一致）。注意：空串会把占位符
                **删除**（str.replace 语义），不是"保留不替换"——旧实现前缀恒读自
                config_for_search_index.json，未配置时同样是删除。
            check_duplicate: `insert_data` 未显式传 check_duplicate 时的缺省（对齐旧
                config `check_duplicate`，生产缺省 True）。`insert_text` 不受影响（恒不查重）。
            is_need_llm: 查重时 LLM 判定分支的缺省开关（对齐旧 config `is_need_llm`，缺省 False）。
            simility_tools: 查重相似度工具（旧 `SimilityTools` 或等价鸭子类型）；
                None 时懒构造（优先旧实现的无 LLM 裸实例，导入失败用内置兜底）。
            category_client: 类目服务客户端（web_search 的 category_names→ids 映射）；
                None 时用未配置 URL 的降级实例（不发 HTTP，映射恒 None）。
        """
        self._repo = repository
        self._embedding = embedding_client
        self._default_index = default_index or repository._default_index
        self._multimodal_prefix = multimodal_prefix or ""
        self._check_duplicate = check_duplicate
        self._is_need_llm = is_need_llm
        self._simility_tools = simility_tools
        self._category = category_client or CategoryClient("")

    @classmethod
    def from_config(cls, config_path: str, index_name: Optional[str] = None) -> "KnowledgeService":
        """从 rebuild config（config_test.json）构造完整 Service。

        cfg 中的 `legacy_search_config_path` 指向旧 `config_for_search_index.json`，是
        multimodal_prefix / check_duplicate / is_need_llm / simility_config_path /
        category_service_url 等业务口径的**唯一来源**（与旧 `SearchDataInterface.__init__`
        读同一份 config，保证行为一致）；缺失时逐项取内置缺省并打 warning。

        默认索引解析顺序：显式 index_name 参数 > cfg["default_index_name"] >
        cfg["test_index_name"]（**测试索引，误用会写脏，选中时打 warning**）> engine config
        的 index_name（同样打 warning，不再静默回退）。
        """
        cfg = load_config(config_path)
        if not index_name:
            index_name = cfg.get("default_index_name")
            if not index_name and cfg.get("test_index_name"):
                index_name = cfg["test_index_name"]
                logger.warning(
                    "from_config 未显式传 index_name 且 cfg 无 default_index_name，"
                    "回退使用测试索引 cfg['test_index_name']=%r——生产接入请显式指定索引！",
                    index_name,
                )
        if not index_name:
            logger.warning(
                "from_config 未能确定默认索引（cfg 缺 default_index_name/test_index_name），"
                "将回退 engine config 的 index_name——请确认这不是误配置！"
            )
        repo = KnowledgeRepository(
            engine_config_path=cfg["engine_config_path"], default_index=index_name
        )
        embedding = build_embedding_client(cfg["embedding_config_path"])

        legacy_cfg = cls._load_legacy_search_cfg(cfg)
        multimodal_prefix = legacy_cfg.get("multimodal_prefix", "") or ""
        if not multimodal_prefix:
            logger.warning(
                "multimodal_prefix 未配置（cfg 缺 legacy_search_config_path 或旧 config 缺该键）。"
                "检索返回的 content 中 `[multimodal_prefix]` 占位符将被替换为空串（即被删除），"
                "多模态文件地址会退化成裸相对路径！"
            )

        simility_tools = None
        if LegacySimilityTools is not None:
            sim_cfg_path = legacy_cfg.get("simility_config_path")
            if not (sim_cfg_path and os.path.exists(sim_cfg_path)):
                sim_cfg_path = None
            try:
                simility_tools = LegacySimilityTools(sim_cfg_path)
            except Exception as exc:  # pragma: no cover - 旧依赖配置损坏
                logger.warning("构造旧 SimilityTools 失败，查重将用无 LLM 兜底: %s", exc)

        category_client = CategoryClient(
            legacy_cfg.get("category_service_url", ""),
            legacy_cfg.get("category_update_time_interval", 36000),
        )
        return cls(
            repo,
            embedding,
            default_index=index_name,
            multimodal_prefix=multimodal_prefix,
            check_duplicate=legacy_cfg.get("check_duplicate", True),
            is_need_llm=legacy_cfg.get("is_need_llm", False),
            simility_tools=simility_tools,
            category_client=category_client,
        )

    @staticmethod
    def _load_legacy_search_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """读取 cfg 引用的旧 config_for_search_index.json；缺失/损坏返回 {} 并告警。"""
        search_cfg_path = cfg.get("legacy_search_config_path") or cfg.get("search_config_path")
        if not search_cfg_path or not os.path.exists(search_cfg_path):
            logger.warning(
                "cfg 未配置 legacy_search_config_path（或文件不存在: %r），"
                "multimodal_prefix/check_duplicate/is_need_llm 等业务口径将取内置缺省",
                search_cfg_path,
            )
            return {}
        try:
            with open(search_cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:  # pragma: no cover
            logger.warning("读取 legacy_search_config_path 失败: %s", exc)
            return {}

    def _get_simility_tools(self) -> Any:
        """懒构造查重相似度工具：优先旧 SimilityTools（无 LLM 裸实例），失败用内置兜底。"""
        if self._simility_tools is None:
            if LegacySimilityTools is not None:
                self._simility_tools = LegacySimilityTools(None)
            else:
                self._simility_tools = _FallbackSimilityTools()
        return self._simility_tools

    # ================= 写 =================
    def insert_text(
        self,
        doc: Dict[str, Any],
        index_name: Optional[str] = None,
        refresh_imm: bool = False,
    ) -> Tuple[bool, str]:
        """插入一条文本文档（自动生成向量与 _id），返回 (是否成功, 消息)。

        **最小插入（新 API）**：不查重、`_prepare_document` 异常原样上抛；缺 `dataset` 时
        用 index_name（缺省 default_index）兜底。需要旧 `insert_data` 的完整契约
        （默认查重 / is_update_data 软删覆盖 / 异常兜成 (False,'数据处理失败')）请用
        :meth:`insert_data`。
        """
        target_index = index_name or self._default_index
        prepared = self._prepare_document(copy.deepcopy(doc), index_name=target_index)
        ok = self._repo.insert(prepared, index_name=index_name, refresh_imm=refresh_imm)
        return (True, "") if ok else (False, "insert failed")

    def insert_data(
        self,
        data: Dict[str, Any],
        check_duplicate: Optional[bool] = None,
        index_name: Optional[str] = None,
        is_update_data: bool = False,
        is_only_title: bool = False,
        basic_threshold: float = 0.7,
        title_basic_threshold: float = 0.95,
        refresh_imm: bool = False,
        is_need_llm: Optional[bool] = None,
    ) -> Tuple[bool, str]:
        """旧 `SearchDataInterface.insert_data` 的完整替代（签名/返回/文案对齐）。

        Args:
            data: 待插入文档（不会被修改；内部 deepcopy）。
            check_duplicate: 是否查重；None 时取构造参数 `check_duplicate`（对齐旧
                config 缺省，生产为 True）。
            is_update_data: 查重命中时 True→软删旧数据（del_flag=1, del_reason=cover_by_new）
                后继续插入；False→跳过插入返回 (False, '数据重复')。
            is_need_llm: 查重 LLM 分支开关；None 取构造参数 `is_need_llm`。
        Returns:
            (成功?, 消息)：成功 (True,'')；重复 (False,'数据重复')；处理失败
            (False,'数据处理失败')；引擎写入失败 (False,'')——与旧实现逐一对齐。

        与旧实现的有意差异（见 docs/CRUD_Legacy_Difference_Issues.md）：
        - 不复刻"往调用方 dict 里塞 `_id=None`"的旧副作用（旧代码想回填生成的 _id 但恒为
          None，且会破坏同一 dict 的二次插入）。
        - 带 `_id` 且缺 `insert_time` 的 upsert 不再整条失败（旧实现 KeyError→'数据处理失败'）。
        """
        if check_duplicate is None:
            check_duplicate = self._check_duplicate
        data = copy.deepcopy(data)
        try:
            data = self._prepare_document(data, index_name=index_name)
        except Exception:
            logger.error("处理数据失败: %s", traceback.format_exc())
            return (False, "数据处理失败")

        is_need_llm = self._is_need_llm if is_need_llm is None else is_need_llm
        if check_duplicate:
            duplicates = self.find_duplicates(
                data,
                is_need_llm=is_need_llm,
                index_name=index_name,
                exclude_self=True,  # 与旧一致：自身命中不算重复（默认按更新数据看待）
                is_only_title=is_only_title,
                basic_threshold=basic_threshold,
                title_basic_threshold=title_basic_threshold,
            )
            if duplicates:
                duplicates_ids = [dup["_id"] for dup in duplicates]
                if is_update_data:
                    # 与旧一致：软删除重复数据后继续插入；软删失败只记日志不阻断。
                    # 已知旧坑（README 陷阱#2）：conditions 用 `_id` 走 terms 过滤在 ES 上是
                    # silent no-op——为保持与旧实现完全一致的线上行为，这里不改用 ids 查询。
                    try:
                        self._repo.update_by_condition(
                            {"del_flag": 1, "del_reason": f'cover_by_new {data.get("_id")}'},
                            [{"_id": duplicates_ids}],
                            index_name=index_name,
                        )
                        logger.info(
                            "数据%s覆盖重复数据, title:%s，已软删除重复数据ID: %s",
                            data.get("_id"), data.get("title"), duplicates_ids,
                        )
                    except Exception as e:
                        logger.error("软删除重复数据失败: %s, 重复数据ID: %s", e, duplicates_ids)
                else:
                    logger.warning(
                        "数据%s重复, title:%s，跳过插入，重复数据ID: %s",
                        data.get("_id"), data.get("title"), duplicates_ids,
                    )
                    return (False, "数据重复")

        return (self._repo.insert(data, index_name=index_name, refresh_imm=refresh_imm), "")

    def batch_insert_data(
        self, data_list: List[Dict[str, Any]], check_duplicate: bool = True
    ) -> List[Tuple[bool, str]]:
        """批量插入；逐条调用 `insert_data`，返回逐条 (成功?, 消息) 列表。

        与旧 `batch_insert_data` 一致：check_duplicate 缺省 True（**不**取配置缺省）。
        """
        results = []
        for data in data_list:
            results.append(self.insert_data(data, check_duplicate))
        return results

    # 新 API 名 alias
    batch_insert = batch_insert_data

    def find_duplicates(
        self,
        data: Dict[str, Any],
        topK: int = 5,
        is_need_llm: bool = True,
        index_name: Optional[str] = None,
        exclude_self: bool = False,
        is_only_title: bool = False,
        basic_threshold: float = 0.7,
        title_basic_threshold: float = 0.95,
    ) -> List[Dict[str, Any]]:
        """查找重复数据（复刻旧 `SearchDataInterface.find_duplicates`）。

        流程：`_prepare_document`（处理失败→返回 []）→ 用 title+content 文本 + 首个 index
        向量 + data_type/platform 属性过滤检索 topK 候选 → 逐候选用 SimilityTools 阈值
        （可选 LLM）判定。`exclude_self=False` 时 `_id` 相同的自身也算重复。

        注意：与旧完全一致地使用**浅 copy**——对已处理过的数据二次 process 时，非 schema
        字段（如首轮补的 `tags`）会经共享的 ext_info dict 泄漏回入参；`insert_data` 默认
        查重路径下最终入库 payload 因此带 `ext_info.tags`。这是旧实现的既有行为，改成
        deepcopy 会让入库文档与旧产物不一致（离线差分测试锁定该 parity）。
        """
        processed_data = data.copy()
        try:
            # 与旧一致：这里不传 index_name（dataset 不做兜底）
            processed_data = self._prepare_document(processed_data)
        except Exception:
            logger.error("处理待查重数据失败: %s", traceback.format_exc())
            return []

        query: Dict[str, Any] = {
            "query": processed_data.get("title", "") + " " + processed_data.get("content", ""),
        }
        if processed_data.get("indexes") and processed_data["indexes"][0].get("embedding"):
            query["vector"] = {"value": processed_data["indexes"][0]["embedding"]}
        # 'unkonw' 为旧实现的原样拼写（作为过滤值参与检索，不能"修正"）
        query["attribute"] = {
            "data_type": processed_data.get("data_type", "unkonw"),
            "platform": processed_data.get("platform", "unkonw"),
        }
        candidates = self._repo.search(query, size=topK, index_name=index_name)

        duplicates = []
        simility_tools = self._get_simility_tools()
        for candidate in candidates:
            if candidate.get("_id") == processed_data.get("_id"):
                if not exclude_self:  # 不排除自身时，已存在的同 _id 数据即为重复
                    duplicates.append(candidate)
                logger.debug("数据%s 已存在", processed_data.get("_id"))
                continue
            if simility_tools.is_simility_knowledge(
                processed_data,
                candidate,
                is_need_llm=is_need_llm,
                is_only_title=is_only_title,
                basic_threshold=basic_threshold,
                title_basic_threshold=title_basic_threshold,
            ):
                duplicates.append(candidate)
        return duplicates

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
            # 与旧 `search_data_by_query` 一致：返回前把 [multimodal_prefix] 占位符替换为配置前缀。
            # 注意：prefix 为空串时 str.replace 会把占位符**删除**（不是"保留不替换"）——
            # 与旧实现行为相同（旧前缀恒读自 config_for_search_index.json，未配置同样是删除）。
            content = doc.get("content")
            if isinstance(content, str) and MULTIMODAL_PREFIX_PLACEHOLDER in content:
                doc["content"] = content.replace(
                    MULTIMODAL_PREFIX_PLACEHOLDER, self._multimodal_prefix
                )
        return candidate_docs, total_num

    def search_text_multi(
        self,
        query_list: List[str],
        index_name: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """多 query 单请求检索（复刻旧 `search_data_by_multi_query`）。

        一条 msearch/search 语句携带多文本+多向量；每 doc 的 similarity 取各 query 相似度
        最大值。主路径异常时回退多线程逐 query 检索（去重合并、按相似度排序、截断 size）。

        与旧实现一致的细节（含已知怪癖，均有测试契约）：
        - 默认 condition_dicts 为 `quality_level=['high']` + `audit_result=[1]` 两组（注意与
          search_text 的 `[1,2]` 不同）；缺 audit_result 的组补 `[1,-1]`（非 `[1,2,-1]`）。
        - **不做** multimodal_prefix 替换（旧主路径就没做；回退路径经 search_text 会替换）。
        - query_list 混有空串时，相似度计算按 query_list 下标取只收录了非空 query 的
          向量列表，下标错位导致部分 doc 相似度记 0（旧实现原样保留）。
        """
        if not query_list:
            logger.warning("query_list 为空，返回空结果")
            return [], 0

        query_embeddings = []
        for query in query_list:
            if query:  # 跳过空字符串
                embedding = self._embedding.text2embedding(query)
                if embedding is not None:
                    query_embeddings.append({"value": embedding})

        search_query: Dict[str, Any] = {
            "query": query_list,
            "vector": query_embeddings if query_embeddings else None,
        }

        idx_arg: Optional[Union[str, List[str]]] = None
        if index_name:
            idx_arg = index_name.split(",") if isinstance(index_name, str) else index_name

        if not condition_dicts:
            condition_dicts = []
            condition_dicts.append({"quality_level": ["high"], "data_type": ["qa"]})
            condition_dicts.append({"audit_result": [1], "data_type": ["qa"]})
        for condition_dict in condition_dicts:
            if "audit_result" not in condition_dict:
                condition_dict["audit_result"] = [1, -1]
        search_query["attribute"] = condition_dicts

        try:
            candidate_docs, total_num = self._repo.search_multi(
                search_query, index_name=idx_arg, size=size * 2
            )
            for doc in candidate_docs:
                max_similarity = 0
                for i, query in enumerate(query_list):
                    if query:
                        query_embedding = (
                            query_embeddings[i]["value"] if i < len(query_embeddings) else None
                        )
                        if query_embedding is not None:
                            similarity = self._cal_similarity(
                                query,
                                query_embedding,
                                doc,
                                search_type=search_type,
                                data_type=data_type,
                                use_synonyms=use_synonyms,
                            )
                            max_similarity = max(max_similarity, similarity)
                doc["similarity"] = max_similarity
            logger.info(
                "多查询搜索完成，查询数量: %d, 结果数量: %d, 总数: %d",
                len(query_list), len(candidate_docs), total_num,
            )
            return candidate_docs, total_num
        except Exception as e:
            logger.error("多查询搜索失败: %s", e)
            logger.error("traceback: %s", traceback.format_exc())
            logger.info("尝试使用多线程方式进行多查询搜索...")
            return self._search_text_multi_threading(
                query_list, idx_arg, condition_dicts, size, search_type, data_type, use_synonyms
            )

    def _search_text_multi_threading(
        self,
        query_list: List[str],
        index_name: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """多线程逐 query 检索回退（复刻旧 `_search_data_by_multi_query_threading`）。

        与旧实现的有意差异：旧回退把已 split 的索引 list 传回 `search_data_by_query`，触发
        `list.split` AttributeError 被逐 query 吞掉——**显式传索引时旧回退恒返回空结果**。
        新 `search_text` 接受 list，回退在该场景返回真实结果（测试契约锁定）。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def search_single_query(query: str) -> Tuple[List[Dict[str, Any]], int]:
            try:
                return self.search_text(
                    query, index_name, condition_dicts, size, search_type, data_type, use_synonyms
                )
            except Exception as e:
                logger.error("查询失败: %s, 错误: %s", query, e)
                return [], 0

        all_results: List[Dict[str, Any]] = []
        total_nums: List[int] = []
        with ThreadPoolExecutor(max_workers=min(len(query_list), 10)) as executor:
            future_to_query = {
                executor.submit(search_single_query, query): query
                for query in query_list
                if query
            }
            for future in as_completed(future_to_query):
                query = future_to_query[future]
                try:
                    results, total_num = future.result()
                    all_results.extend(results)
                    total_nums.append(total_num)
                except Exception as e:  # pragma: no cover - search_single_query 已兜底
                    logger.error("处理查询结果失败: %s, 错误: %s", query, e)

        # 按 _id 去重合并 → 按相似度降序 → 截断 size（与旧一致；total 取各 query 最大值）
        seen_ids = set()
        merged_results = []
        for doc in all_results:
            doc_id = doc.get("_id")
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged_results.append(doc)
        merged_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        final_results = merged_results[:size]
        total_num = max(total_nums) if total_nums else 0
        logger.info(
            "多线程搜索完成，查询数量: %d, 去重后结果数量: %d, 返回数量: %d",
            len(query_list), len(merged_results), len(final_results),
        )
        return final_results, total_num

    def web_search(
        self,
        query: str,
        client: Optional[str] = None,
        index_name: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        page_size: Optional[int] = None,
        page_num: int = 1,
        score_threshold: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Web 管理端分页检索（复刻旧 `web_search_data`）。

        与旧实现一致的行为：
        - 允许空 query（不 embed，纯属性过滤 match_all + del_flag=0）。
        - condition_dicts 缺省为 []（**不**注入 search_text 的默认质量/审核条件）。
        - `category_names` → `category_ids`：经注入的 CategoryClient 按 client（缺省取第一个
          索引名）做全路径名映射；映射不到的丢弃；与显式 `category_ids` 合并。
        - page_size 缺省 10000；分页 + score_threshold 由底层 `search_multi_by_page` 完成。
        - 返回前 content 做 `[multimodal_prefix]` 替换；score 归一化 `min(score/5.0, 1.0)`。
        """
        if query:
            query_embedding = self._embedding.text2embedding(query)
            search_query: Dict[str, Any] = {
                "query": query,
                "vector": {"value": query_embedding},
            }
        else:
            search_query = {}

        idx_arg: Optional[Union[str, List[str]]] = None
        first_index_name = None
        if index_name:
            idx_arg = index_name.split(",") if isinstance(index_name, str) else list(index_name)
            first_index_name = idx_arg[0] if idx_arg else None

        if not condition_dicts:
            condition_dicts = []

        client = client or first_index_name

        for condition_dict in condition_dicts:
            category_ids: List[Any] = []
            if "category_names" in condition_dict:
                cate_names = (
                    condition_dict["category_names"]
                    if isinstance(condition_dict["category_names"], list)
                    else [condition_dict["category_names"]]
                )
                trans_ids = [
                    self._category.map_cate_name_to_id(client, category_name)
                    for category_name in cate_names
                ]
                trans_ids = [trans_id for trans_id in trans_ids if trans_id]
                category_ids.extend(trans_ids)
                condition_dict.pop("category_names")
            if "category_ids" in condition_dict:
                cate_ids = (
                    condition_dict["category_ids"]
                    if isinstance(condition_dict["category_ids"], list)
                    else [condition_dict["category_ids"]]
                )
                category_ids.extend(cate_ids)
                condition_dict.pop("category_ids")
            if category_ids:
                condition_dict["category_ids"] = category_ids
        search_query["attribute"] = condition_dicts

        if not page_size:
            page_size = 10000
        candidate_docs, total_num = self._repo.search_by_page(
            search_query,
            index_name=idx_arg,
            size=page_size,
            page_num=page_num,
            score_threshold=score_threshold,
        )
        for doc in candidate_docs:
            if "content" in doc and isinstance(doc["content"], str):
                doc["content"] = doc["content"].replace(
                    MULTIMODAL_PREFIX_PLACEHOLDER, self._multimodal_prefix
                )
            if "score" in doc:
                doc["score"] = min(doc["score"] / 5.0, 1.0)
        return candidate_docs, total_num

    def get(self, data_id: str, index_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按 _id 取文档（透传仓库 get）。"""
        return self._repo.get(data_id, index_name=index_name)

    # ================= 旧 SearchDataInterface 兼容 alias（旧参数名/顺序） =================
    def search_data_by_query(
        self,
        query: str,
        index_names: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """旧名兼容：等价 `search_text`（旧关键字参数名 index_names）。"""
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
        index_names: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        size: int = 10,
        search_type: str = "qa",
        data_type: str = "text",
        use_synonyms: bool = False,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """旧名兼容：等价 `search_text_multi`。"""
        return self.search_text_multi(
            query_list,
            index_name=index_names,
            condition_dicts=condition_dicts,
            size=size,
            search_type=search_type,
            data_type=data_type,
            use_synonyms=use_synonyms,
        )

    def web_search_data(
        self,
        query: str,
        client: Optional[str] = None,
        index_names: Optional[Union[str, List[str]]] = None,
        condition_dicts: Optional[List[Dict[str, Any]]] = None,
        page_size: Optional[int] = None,
        page_num: int = 1,
        score_threshold: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """旧名兼容：等价 `web_search`。"""
        return self.web_search(
            query,
            client=client,
            index_name=index_names,
            condition_dicts=condition_dicts,
            page_size=page_size,
            page_num=page_num,
            score_threshold=score_threshold,
        )

    def update_data(self, data_id: str, data: Dict[str, Any]) -> bool:
        """旧名兼容：原样透传局部更新（**不**刷新 update_time、不重算向量，用默认索引）。

        与旧 `update_data` 一致：doc 内含 `_id` 等 ES 元字段时更新会失败返回 False。
        需要增强语义（刷新 update_time / 重算向量 / 指定索引）请用 :meth:`update`。
        """
        return self._repo.update_by_id(data_id, data)

    def delete_data(
        self,
        data_id: str,
        index_names: Optional[Union[str, List[str]]] = None,
        refresh: bool = False,
    ) -> bool:
        """旧名兼容：等价 `delete`。"""
        return self._repo.delete(data_id, index_name=index_names, refresh=refresh)

    def search_data(
        self,
        query: Dict[str, Any],
        size: Optional[int] = None,
        index_names: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """旧名兼容：query_dict 级原始混合检索（透传 `repo.search`）。"""
        return self._repo.search(query, size, index_name=index_names)

    def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
        """旧名兼容：等价 `get`（用默认索引）。"""
        return self._repo.get(data_id)

    def update_data_value(
        self,
        index_name: str,
        update_value_dict: Dict[str, Any],
        conditions: List[Dict[str, Any]],
    ) -> bool:
        """旧名兼容：按条件批量更新（旧参数顺序 index_name 在前）。"""
        return self._repo.update_by_condition(update_value_dict, conditions, index_name=index_name)

    def get_unique_values(
        self,
        index_name: str,
        field_name: str,
        size: int = 10000,
        include_doc_count: bool = False,
        extra_query: Optional[Dict[str, Any]] = None,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """旧名兼容：字段唯一值聚合（旧参数顺序 index_name 在前）。"""
        return self._repo.get_unique_values(
            field_name,
            index_name=index_name,
            size=size,
            include_doc_count=include_doc_count,
            extra_query=extra_query,
        )

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

        # 2. is_audit → audit_result；audit_result 缺省仅新建，但非法值矫正**不分新旧**——
        #    与旧一致（si:437-439 无条件重置），保证带 _id 的 upsert 传非法值时仍会被矫正为 -1，
        #    从而能被默认检索条件的 audit_result∈[1,2,-1] 组命中（检索可见性契约）。
        #    注意旧实现按 truthiness 判断：audit_result=0/None/'' 不触发矫正，原样保留。
        if "is_audit" in data:
            data["audit_result"] = data.pop("is_audit")
        if "audit_result" not in data and is_new:
            data["audit_result"] = -1
        if data.get("audit_result") and data["audit_result"] not in VALID_AUDIT_RESULTS:
            logger.warning("audit_result 非法 %r，重置为 -1", data["audit_result"])
            data["audit_result"] = -1
        # quality_level 缺省与矫正都仅新建（与旧一致：带 _id 时不动）
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

        # 7. keywords（jieba.analyse.textrank，无外部 LLM）；缺失时基于 title+content 生成。
        #    与旧一致（si:502-510）：只吞 ImportError（工具缺失跳过），jieba 运行期异常向上抛
        #    ——insert_data 会兜成 (False,'数据处理失败')，insert_text 直接抛给调用方。
        if not data.get("keywords") and (data.get("title") or data.get("content")):
            if legacy_gen_keyword_by_title_content is not None:
                try:
                    raw = legacy_gen_keyword_by_title_content(
                        data.get("title", ""), data.get("content", ""), topK=5
                    )
                    keywords = [word_info["word"] for word_info in raw]
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

        # 11. from_type / from_type_norm / tags。
        #     from_type 缺省仅新建；**非字符串转 str 不分新旧**（与旧一致 si:544-546，带 _id 的
        #     upsert 同样转换，避免与 keyword mapping 冲突）。from_type_norm 异常不吞
        #     （与旧一致，交由 insert_data 兜成 '数据处理失败'）。
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
        """拼接多模态内容；逐行复刻旧 `SearchDataInterface.join_multimodal_contents`（si:390-407）。

        image/video/audio/file 类型的 path 以字面 `[multimodal_prefix]` 占位，等检索返回前
        再替换为构造时注入的真实前缀（与旧实现一致）。

        边界语义与旧完全一致、**不做"顺手修复"**（拼接结果参与 content_embedding 与
        gen_data_id，任何偏差都会改 _id）：text 项缺 content 时，首项使 content 变为 None，
        非首项拼出字面 "\\nNone"。
        """
        content = ""
        for file_info in multimodal_contents:
            if file_info.get("type") == "text":
                content = (
                    f"{content}\n{file_info.get('content')}"
                    if content
                    else file_info.get("content")
                )
            elif file_info.get("type") in MULTIMODAL_FILE_TYPES:
                address = (
                    f'{MULTIMODAL_PREFIX_PLACEHOLDER}{file_info["path"]}'
                    if file_info.get("path")
                    else file_info.get("url")
                )
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
