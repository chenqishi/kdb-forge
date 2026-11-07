"""Unified knowledge project. Legacy forge exports are thin protocol adapters."""
from pathlib import Path as _Path
import sys as _sys

# The retained legacy imports live in this checkout, never in another old repo.
_checkout_root = _Path(__file__).resolve().parents[2]
if (_checkout_root / "knowledge_interface_tools").is_dir() and str(_checkout_root) not in _sys.path:
    _sys.path.insert(0, str(_checkout_root))

__all__ = ["KnowledgeRepository", "KnowledgeService", "SearchDataInterface"]


def __getattr__(name):
    if name == "KnowledgeRepository":
        from .crud.repository import KnowledgeRepository
        return KnowledgeRepository
    if name == "KnowledgeService":
        from .services.forge_compat.adapter import KnowledgeService
        return KnowledgeService
    if name == "SearchDataInterface":
        from .retrieval.application.search_index_data_interface import SearchDataInterface
        return SearchDataInterface
    raise AttributeError(name)
