from kdb.retrieval.engines.factory import EsSearchInterface
from kdb.retrieval.engines.protocol import SearchEngine

def load_search_engine(self, config_path: str, **kwargs) -> SearchEngine:
    """
    加载搜索引擎
    Args:
        config_path: 搜索引擎配置文件路径
        **kwargs: 其他参数
    Returns:
        SearchEngine: 搜索引擎实例
    """
    # EsSearchInterface需要的参数列表
    es_params = [
        'hosts',
        'index_name',
        'username',
        'password',
        'vector_fields'
    ]

    # 从kwargs中提取ES相关参数
    es_kwargs = {
        key: kwargs.pop(key)
        for key in es_params
        if key in kwargs
    }

    # 如果提供了config_path，添加到参数中
    if config_path:
        es_kwargs['config_path'] = config_path

    # 其他未被提取的kwargs参数会作为extra_params传入
    if kwargs:
        es_kwargs['extra_params'] = kwargs

    return EsSearchInterface(**es_kwargs)
