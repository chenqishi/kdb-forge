from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Union

def search_data(self, query: Dict[str, Any],
               size: Optional[int] = None, index_names: Optional[Union[str, List[str]]] = None) -> List[Dict[str, Any]]:
    """
    搜索数据
    Args:
        query: 查询条件
        size: 返回结果数量限制
    Returns:
        List[Dict]: 搜索结果列表
    """
    return self.engine.search(query, size, index_names=index_names)


def get_data_by_id(self, data_id: str) -> Optional[Dict[str, Any]]:
    """
    根据ID获取数据
    Args:
        data_id: 数据ID
    Returns:
        Optional[Dict]: 数据内容，不存在则返回None
    """
    return self.engine.get(data_id)


def search_data_by_query(self, query:str, index_names:str=None, condition_dicts:List[Dict[str, Any]]=None, size:int=10, search_type:str='qa',
                         data_type:str='text', use_synonyms=False):
    """
    根据query和attribute_dict搜索数据
    Args:
        query: 查询文本
        attribute_dict: 限制字典
    Returns:
        List[Dict]: 搜索结果列表
    """

    query_embedding = self.embedding_tools.text2embedding(query)
    search_query = {
        "query": query,
        "vector": {"value": query_embedding},
    }
    if index_names:
        index_names = index_names.split(',')
    if not condition_dicts:
        condition_dicts = []
        condition_dicts.append({'quality_level': ['high'], 'data_type': ['qa']})
        condition_dicts.append({'audit_result': [1, 2], 'data_type': ['qa']})
    for condition_dict in condition_dicts:
        if 'audit_result' not in condition_dict:
            condition_dict['audit_result'] = [1, 2, -1]
    search_query['attribute'] = condition_dicts
    # size*2 是候选总预算：legacy 模式每索引取这么多；dual 模式每索引每路各取一半，合计不变
    candidate_docs, total_num = self.engine.search_multi(search_query, index_names=index_names, size=size * 2)
    #logger.info(f"搜索结果数量: {len(candidate_docs)}")
    for doc in candidate_docs:
        doc['similarity'] = self._cal_similarity(query, query_embedding, doc, search_type=search_type, data_type=data_type, use_synonyms=use_synonyms)
        self.render_multimodal_urls(doc)
    #candidate_docs.sort(key=lambda x: x['similarity'], reverse=True)
    return candidate_docs, total_num
