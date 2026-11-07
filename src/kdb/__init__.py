"""Knowledge project using the existing business service interfaces."""
__all__ = ["SearchDataInterface"]


def __getattr__(name):
    if name == "SearchDataInterface":
        from .retrieval.application.search_index_data_interface import SearchDataInterface
        return SearchDataInterface
    raise AttributeError(name)
