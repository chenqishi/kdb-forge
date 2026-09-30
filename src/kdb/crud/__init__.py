"""CRUD 层：纯向量 Repository + 文本级 Service。"""

from kdb.crud.repository import KnowledgeRepository
from kdb.crud.service import KnowledgeService, SearchDataInterface

__all__ = ["KnowledgeRepository", "KnowledgeService", "SearchDataInterface"]
