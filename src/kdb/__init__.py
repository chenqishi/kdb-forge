"""Unified knowledge project. Legacy forge exports are thin protocol adapters."""
__all__ = ["KnowledgeRepository", "KnowledgeService", "SearchDataInterface"]


def __getattr__(name):
    if name == "KnowledgeRepository":
        from .services.forge_compat.repository import KnowledgeRepository
        return KnowledgeRepository
    if name == "KnowledgeService":
        from .services.forge_compat.adapter import KnowledgeService
        return KnowledgeService
    if name == "SearchDataInterface":
        from .retrieval.application.search_index_data_interface import SearchDataInterface
        return SearchDataInterface
    raise AttributeError(name)
