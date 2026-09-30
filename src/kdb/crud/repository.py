"""KnowledgeRepository —— 纯向量 CRUD 层。

职责（单一）：把"向量已就绪的文档"原样进出 ES，封装 ES 8.17 路由引擎。
**不**生成 embedding、**不**生成 _id、**不**做去重/类目/质量等业务过滤——这些在 Service 或后续 pipeline。

默认引擎使用 ES 8.17 client，并按 index 路由到 Serverless/PaaS；查询 DSL、mapping
与双路 BM25/native KNN 召回由重构版引擎实现。
query_dict 通用结构：`{"query": <text>, "vector": {"value": <list[float]>}, "attribute": <dict|list[dict]>}`。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from kdb.legacy_bridge import build_legacy_engine

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
            engine: ES8.17 `RoutedLegacyEngine` 或兼容鸭子类型实例。为 None 时用 engine_config_path 构造。
            engine_config_path: config_es_engine.json 路径（engine 为空时必填）。
            default_index: 默认索引名；方法未显式传 index_name 时使用。为空时取 engine 内部 index_name。
        """
        if engine is None:
            if not engine_config_path:
                raise ValueError("engine 与 engine_config_path 不能同时为空")
            engine = build_legacy_engine(config_path=engine_config_path, index_name=default_index)
        self._engine = engine
        # 兼容旧引擎把实现放在 _impl 的情况；路由引擎自身的 index_name 同样有效
        impl = getattr(engine, "_impl", None) or engine
        self._default_index = default_index or getattr(impl, "index_name", None)

    # ---- 辅助 ----
    def _idx(self, index_name: Optional[Union[str, List[str]]]):
        return index_name if index_name is not None else self._default_index

    # ---- 索引管理 ----
    def ensure_index(self, index_name: Optional[str] = None) -> None:
        """确保索引存在（新建为 ES8 native KNN mapping；旧未索引向量拒绝复用）。"""
        target = self._idx(index_name)
        routed_ensure = getattr(self._engine, "_ensure_index", None)
        if routed_ensure:
            routed_ensure(target)
            return
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
        委托 ES8 `engine.insert`（校验维度、过滤零向量、update(doc_as_upsert=True)）。
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
            target = self._idx(index_name)
            get_client = getattr(self._engine, "get_client_by_index", None)
            client = get_client(target) if get_client else impl.es
            client.indices.refresh(index=target)
        except Exception as exc:  # pragma: no cover
            logger.warning("强制刷新索引失败: %s", exc)

    def get_client_by_index(self, index_name: Optional[str] = None) -> Any:
        """返回指定 index 对应的 ES client，供少量运维/刷新场景使用。"""
        target = self._idx(index_name)
        get_client = getattr(self._engine, "get_client_by_index", None)
        if get_client:
            return get_client(target)
        impl = getattr(self._engine, "_impl", self._engine)
        return impl.es

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
        recall_mode: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """多向量/多索引混合检索，返回 (docs, total_num)。

        默认使用配置中的 dual 模式；传入 recall_mode 时可显式切换为旧 legacy 融合模式。
        """
        kwargs = {
            "index_names": self._idx(index_name),
            "size": size,
            "page_num": page_num,
        }
        if recall_mode is not None:
            kwargs["recall_mode"] = recall_mode
        return self._engine.search_multi(query_dict, **kwargs)

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
