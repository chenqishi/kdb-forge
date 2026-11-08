from kdb.shared.similarity.vectors import cosine_similarity
from typing import Any
from typing import Dict
from typing import List
import logging
logger = logging.getLogger('kdb.retrieval.application.search_index_data_interface')

def _cal_title_similarity(self, query: str, query_embedding: List[float], doc: Dict[str, Any], use_synonyms=False) -> float:
    """
    计算query和data的title相似度
    """
    title_similarity = 0
    if doc.get('title') and doc.get('title_embedding'):
        title_similarity = cosine_similarity(query_embedding, doc['title_embedding'])
    if not use_synonyms:
        return title_similarity
    synonyms_titles = set(doc.get('synonyms_title', []))
    max_synonyms_similarity = 0
    for index_info in doc.get('indexes', []):
        text = index_info.get('text')
        if text and text in synonyms_titles and index_info.get('embedding'):
            synonyms_similarity = cosine_similarity(query_embedding, index_info['embedding'])
            max_synonyms_similarity = max(max_synonyms_similarity, synonyms_similarity)
    logger.debug(f"query: {query}, doc: {doc.get('title')}, title_similarity: {title_similarity}, max_synonyms_similarity: {max_synonyms_similarity}")
    return max(title_similarity, max_synonyms_similarity)


def _cal_similarity(self, query: str, query_embedding: List[float], doc: Dict[str, Any], search_type: str='qa', data_type: str='text', use_synonyms=False) -> float:
    """
    计算query和data的相似度
    Args:
        query: 查询文本
        query_embedding: 查询文本的embedding
        doc: 数据
    """
    title_similarity = self._cal_title_similarity(query, query_embedding, doc, use_synonyms)

    if doc.get('content') and doc.get('content_embedding'):
        content_similarity = cosine_similarity(query_embedding, doc['content_embedding'])
    else:
        content_similarity = 0
    if search_type == 'qa':
        if doc.get('title'): # 有title和无title的数据不放在一块排序
            similarity = title_similarity + 0.2 * content_similarity
        else:
            similarity = content_similarity
    else:
        similarity = max(title_similarity, content_similarity)
    if 'image' in data_type: # 如果数据中有图片，考虑图片相似度的影响
        image_similarity = 0

        if doc.get('image_indexes'):
            for image_index in doc['image_indexes']:
                if image_index.get('embedding'):
                    image_similarity = max(image_similarity, cosine_similarity(query_embedding, image_index['embedding']))
        similarity = max(similarity, image_similarity)

    logger.debug(f"query: {query}, doc: {doc.get('title')}, use_synonyms: {use_synonyms}, search_type: {search_type}, similarity: {similarity}, title_similarity: {title_similarity}, content_similarity: {content_similarity}")
    return similarity
