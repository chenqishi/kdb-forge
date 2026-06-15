"""KnowledgeRepository —— 纯向量 CRUD 层。

职责（单一）：把"向量已就绪的文档"原样进出 ES，封装并复用旧 `EsSearchInterface`。
**不**生成 embedding、**不**生成 _id、**不**做去重/类目/质量等业务过滤——这些在 Service 或后续 pipeline。

所有方法都委托给底层旧引擎（`EsSearchInterface` 工厂，自动适配 ES7.x / OpenSearch2.19）。
query_dict 通用结构：`{"query": <text>, "vector": {"value": <list[float]>}, "attribute": <dict|list[dict]>}`。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from kdb.legacy_bridge import EsSearchInterface

logger = logging.getLogger(__name__)


class KnowledgeRepository:
    """纯向量知识库读写接口。"""

    def __init__(
        self,
        engine: Any = None,
        engine_config_path: Optional[str] = None,
        default_index: Optional[str] = None,
    ) -> None:
        """
        Args:
            engine: 旧 `EsSearchInterface` 实例（鸭子类型）。为 None 时用 engine_config_path 构造。
            engine_config_path: config_es_engine.json 路径（engine 为空时必填）。
            default_index: 默认索引名；方法未显式传 index_name 时使用。为空时取 engine 内部 index_name。
        """
        if engine is None:
            if not engine_config_path:
                raise ValueError("engine 与 engine_config_path 不能同时为空")
            engine = EsSearchInterface(config_path=engine_config_path, index_name=default_index)
        self._engine = engine
        # 旧引擎把实现放在 _impl，其 index_name 为权威默认索引
        self._default_index = default_index or getattr(
            getattr(engine, "_impl", engine), "index_name", None
        )

    # ---- 辅助 ----
    def _idx(self, index_name: Optional[Union[str, List[str]]]):
        return index_name if index_name is not None else self._default_index

    # ---- 索引管理 ----
    def ensure_index(self, index_name: Optional[str] = None) -> None:
        """确保索引存在（用旧权威 mapping 创建；已存在则增量加字段，不改已有字段）。"""
        target = self._idx(index_name)
        # 旧 _ensure_index 在 _impl 上
        impl = getattr(self._engine, "_impl", self._engine)
        impl._ensure_index(target)

    # ---- 写 ----
    def insert(
        self,
        data: Dict[str, Any],
        index_name: Optional[str] = None,
        refresh_imm: bool = False,
    ) -> bool:
        """插入/upsert 一条文档。

        前置约定：data 必须含 `_id`；`indexes[].embedding` 已是 1024 维 list。
        委托旧 `engine.insert`（其内部校验维度、过滤零向量、es.update(doc_as_upsert=True)）。
        """
        return self._engine.insert(data, index_names=self._idx(index_name), refresh_imm=refresh_imm)

    def update_by_id(
        self,
        data_id: str,
        data: Dict[str, Any],
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> bool:
        """按 _id 局部更新（部分字段合并，非 upsert）。委托旧 `engine.update`。

        旧 `engine.update` 不接受 refresh，但在 Aliyun ES serverless 上 get-by-id
        并非严格实时——更新后立即读取可能仍返回旧版本。这里 refresh=True 时
        额外强制刷新索引，保证 read-after-write 一致性（测试与对齐场景必需）。
        """
        ok = self._engine.update(data_id, data, index_names=self._idx(index_name))
        if ok and refresh:
            self._force_refresh(index_name)
        return ok

    def update_by_condition(
        self,
        update_value_dict: Dict[str, Any],
        conditions: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> bool:
        """按条件批量更新字段（如软删除 del_flag=1）。委托旧 `engine.update_value`。"""
        ok = self._engine.update_value(self._idx(index_name), update_value_dict, conditions)
        if ok and refresh:
            self._force_refresh(index_name)
        return ok

    def _force_refresh(self, index_name: Optional[str] = None) -> None:
        """强制刷新索引，使最近写入立即可见。"""
        impl = getattr(self._engine, "_impl", self._engine)
        try:
            impl.es.indices.refresh(index=self._idx(index_name))
        except Exception as exc:  # pragma: no cover
            logger.warning("强制刷新索引失败: %s", exc)

    def delete(
        self,
        data_id: str,
        index_name: Optional[str] = None,
        refresh: bool = False,
    ) -> bool:
        """按 _id 硬删除。委托旧 `engine.delete`。

        旧 `engine.delete` 已传 refresh，但实测 Aliyun ES serverless 在高频
        操作下仍可能 read-after-delete 看到旧版本，故 refresh=True 时额外
        强制刷新索引一次，保证立即不可见。
        """
        ok = self._engine.delete(data_id, index_names=self._idx(index_name), refresh=refresh)
        if ok and refresh:
            self._force_refresh(index_name)
        return ok

    # ---- 读 ----
    def get(self, data_id: str, index_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按 _id 取文档；返回 `{"_id":..., **_source}` 或 None。委托旧 `engine.get`。"""
        return self._engine.get(data_id, index_names=self._idx(index_name))

    def search(
        self,
        query_dict: Dict[str, Any],
        size: int = 10,
        index_name: Optional[Union[str, List[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """单引擎原始混合检索（不重排）。委托旧 `engine.search`。"""
        return self._engine.search(query_dict, size, index_names=self._idx(index_name))

    def search_multi(
        self,
        query_dict: Dict[str, Any],
        index_name: Optional[Union[str, List[str]]] = None,
        size: int = 10,
        page_num: int = 1,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """多向量/多索引混合检索，返回 (docs, total_num)。委托旧 `engine.search_multi`。"""
        return self._engine.search_multi(
            query_dict, index_names=self._idx(index_name), size=size, page_num=page_num
        )

    def search_by_page(
        self,
        query_dict: Dict[str, Any],
        index_name: Optional[Union[str, List[str]]] = None,
        size: int = 10,
        page_num: int = 1,
        score_threshold: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页 + score_threshold 过滤检索，返回 (docs, total_num)。委托旧 `engine.search_multi_by_page`。"""
        return self._engine.search_multi_by_page(
            query_dict,
            index_names=self._idx(index_name),
            size=size,
            page_num=page_num,
            score_threshold=score_threshold,
        )

    def get_unique_values(
        self,
        field_name: str,
        index_name: Optional[str] = None,
        size: int = 10000,
        include_doc_count: bool = False,
        extra_query: Optional[Dict[str, Any]] = None,
    ) -> Union[List[str], List[Dict[str, Any]]]:
        """聚合获取某字段唯一值集合。委托旧 `engine.get_unique_values`。"""
        return self._engine.get_unique_values(
            self._idx(index_name), field_name, size, include_doc_count, extra_query
        )
