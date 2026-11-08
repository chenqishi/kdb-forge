from typing import Any
from typing import Dict
from typing import List
from typing import Tuple
import logging
import traceback
logger = logging.getLogger('kdb.retrieval.application.search_index_data_interface')

def search_data_by_multi_query(self, query_list: List[str], index_names: str=None, condition_dicts: List[Dict[str, Any]]=None, size: int=10,
                               search_type: str='qa', data_type: str='text', use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]:
    """
    根据多个query搜索数据，使用一条ES语句实现
    Args:
        query_list: 查询文本列表
        index_names: 索引名称，多个索引用逗号分隔
        condition_dicts: 限制条件字典列表
        size: 返回结果数量
        search_type: 搜索类型，默认为'qa'
        data_type: 数据类型，默认为'text'
        use_synonyms: 是否使用同义词
    Returns:
        Tuple[List[Dict], int]: (搜索结果列表, 总数量)
    """
    if not query_list:
        logger.warning("query_list为空，返回空结果")
        return [], 0

    # 为每个query生成embedding
    query_embeddings = []
    for query in query_list:
        if query:  # 跳过空字符串
            embedding = self.embedding_tools.text2embedding(query)
            if embedding is not None:
                query_embeddings.append({"value": embedding})

    # 构建搜索query，使用list格式传递多个query和多个vector
    search_query = {
        "query": query_list,  # 传递查询列表
        "vector": query_embeddings if query_embeddings else None,  # 传递向量列表
    }

    # 处理索引名称
    if index_names:
        index_names = index_names.split(',')

    # 设置默认条件
    if not condition_dicts:
        condition_dicts = []
        condition_dicts.append({'quality_level': ['high'], 'data_type': ['qa']})
        condition_dicts.append({'audit_result': [1], 'data_type': ['qa']})

    # 确保每个条件都包含audit_result
    for condition_dict in condition_dicts:
        if 'audit_result' not in condition_dict:
            condition_dict['audit_result'] = [1, -1]

    search_query['attribute'] = condition_dicts

    # 调用底层的search_multi，它现在支持query和vector为list
    try:
        candidate_docs, total_num = self.engine.search_multi(search_query, index_names=index_names, size=size * 2)

        # 为每个文档计算相似度
        # 这里需要对每个query都计算一次相似度，取最大值
        for doc in candidate_docs:
            max_similarity = 0
            for i, query in enumerate(query_list):
                if query:
                    query_embedding = query_embeddings[i]["value"] if i < len(query_embeddings) else None
                    if query_embedding is not None:
                        similarity = self._cal_similarity(query, query_embedding, doc,
                                                        search_type=search_type,
                                                        data_type=data_type,
                                                        use_synonyms=use_synonyms)
                        max_similarity = max(max_similarity, similarity)
            doc['similarity'] = max_similarity
            self.render_multimodal_urls(doc)

        logger.info(f"多查询搜索完成，查询数量: {len(query_list)}, 结果数量: {len(candidate_docs)}, 总数: {total_num}")
        return candidate_docs, total_num

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"多查询搜索失败: {str(e)}")
        logger.error(f"traceback: {tb}")
        # 如果方法1失败，使用多线程方式（回退方案）
        logger.info("尝试使用多线程方式进行多查询搜索...")
        return self._search_data_by_multi_query_threading(query_list, index_names, condition_dicts, size,
                                                         search_type, data_type, use_synonyms)


def _search_data_by_multi_query_threading(self, query_list: List[str], index_names: str=None,
                                         condition_dicts: List[Dict[str, Any]]=None, size: int=10,
                                         search_type: str='qa', data_type: str='text',
                                         use_synonyms=False) -> Tuple[List[Dict[str, Any]], int]:
    """
    使用多线程方式进行多查询搜索（回退方案）
    Args:
        query_list: 查询文本列表
        index_names: 索引名称
        condition_dicts: 限制条件字典列表
        size: 返回结果数量
        search_type: 搜索类型
        data_type: 数据类型
        use_synonyms: 是否使用同义词
    Returns:
        Tuple[List[Dict], int]: (搜索结果列表, 总数量)
    """
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import as_completed

    def search_single_query(query: str) -> Tuple[List[Dict[str, Any]], int]:
        """搜索单个query"""
        try:
            return self.search_data_by_query(query, index_names, condition_dicts, size,
                                            search_type, data_type, use_synonyms)
        except Exception as e:
            logger.error(f"查询失败: {query}, 错误: {str(e)}")
            return [], 0

    # 使用线程池并发执行查询
    all_results = []
    total_nums = []

    with ThreadPoolExecutor(max_workers=min(len(query_list), 10)) as executor:
        future_to_query = {executor.submit(search_single_query, query): query
                         for query in query_list if query}

        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                results, total_num = future.result()
                all_results.extend(results)
                total_nums.append(total_num)
            except Exception as e:
                logger.error(f"处理查询结果失败: {query}, 错误: {str(e)}")

    # 去重合并结果（根据_id去重）
    seen_ids = set()
    merged_results = []
    for doc in all_results:
        doc_id = doc.get('_id')
        if doc_id not in seen_ids:
            seen_ids.add(doc_id)
            merged_results.append(doc)

    # 按相似度排序
    merged_results.sort(key=lambda x: x.get('similarity', 0), reverse=True)

    # 截取前size个结果
    final_results = merged_results[:size]
    total_num = max(total_nums) if total_nums else 0

    logger.info(f"多线程搜索完成，查询数量: {len(query_list)}, 去重后结果数量: {len(merged_results)}, 返回数量: {len(final_results)}")
    return final_results, total_num
