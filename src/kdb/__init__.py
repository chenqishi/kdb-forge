"""kdb —— Knowledge Database Builder（重构版）。

重构第一步：把知识库增删改查（CRUD）抽取成高内聚低耦合的独立模块。
- crud.repository.KnowledgeRepository：纯向量 CRUD（封装 ES8.17 native 路由引擎）
- crud.service.KnowledgeService：文本级 CRUD（注入 embedding 客户端）
"""

from importlib import import_module

__version__ = "0.1.0"

__all__ = ["KnowledgeRepository", "KnowledgeService", "SearchDataInterface"]


def __getattr__(name):
    """Keep health/dry-run imports independent of the CRUD dependencies."""
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module("kdb.crud"), name)
    globals()[name] = value
    return value
