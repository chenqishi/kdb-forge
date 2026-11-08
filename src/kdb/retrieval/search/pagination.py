from typing import Any
from typing import Dict
from typing import List

def web_search_data(self, query: str, client:str = None, index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, page_size: int=None, page_num: int=1, score_threshold: float=None) -> List[Dict[str, Any]]:
    """
    根据query和attribute_dict搜索数据
    Args:
        query: 查询文本
        attribute_dict: 限制字典
    """
    if query:
        query_embedding = self.embedding_tools.text2embedding(query)
        search_query = {
            "query": query,
            "vector": {"value": query_embedding},
        }
    else:
        search_query = {}
    if index_names:
        index_names = index_names.split(',')
        first_index_name = index_names[0]
    else:
        first_index_name = None
    if not condition_dicts:
        condition_dicts = []
    #for condition_dict in condition_dicts:
    #    if 'tags' in condition_dict:
    #        condition_dict['keywords'] = condition_dict.pop('tags')

    client = client or first_index_name

    for condition_dict in condition_dicts:
        category_ids = []
        if 'category_names' in condition_dict:
            cate_names = condition_dict['category_names'] if isinstance(condition_dict['category_names'], list) else [condition_dict['category_names']]
            trans_ids = [self.map_cate_name_to_id(client, category_name) for category_name in cate_names]
            trans_ids = [trans_id for trans_id in trans_ids if trans_id]
            category_ids.extend(trans_ids)
            condition_dict.pop('category_names')
        if 'category_ids' in condition_dict:
            cate_ids = condition_dict['category_ids'] if isinstance(condition_dict['category_ids'], list) else [condition_dict['category_ids']]
            category_ids.extend(cate_ids)
            condition_dict.pop('category_ids')
        if category_ids:
            condition_dict['category_ids'] = category_ids
    search_query['attribute'] = condition_dicts
    if not page_size:
        page_size = 10000
    candidate_docs, total_num = self.engine.search_multi_by_page(search_query, index_names=index_names, size=page_size, page_num=page_num, score_threshold=score_threshold)
    for doc in candidate_docs:
        self.render_multimodal_urls(doc)
        if "score" in doc:
            doc["score"] = min(doc["score"] / 5.0, 1.0)
        #doc['tags'] = doc.get('keywords', [])
    #candidate_docs.sort(key=lambda x: x['similarity'], reverse=True)
    return candidate_docs, total_num
