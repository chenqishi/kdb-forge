from kdb.shared.clients import embedding_tools
from kdb.shared.clients import similarity as simility_tools
import logging
import numpy as np
import re
from typing import Dict, List, Optional, Any

# 可选引入faiss，如不可用则回退到线性检索
try:
    import faiss  # type: ignore
    _faiss_available = True
except Exception:
    _faiss_available = False

def regular_content(content: str) -> str:
    """
    对内容进行规则化清洗
    1. 转换为全小写
    2. 将多余空白符号（空格、换行、制表符等）统一转换为单个空格
    
    Args:
        content: 待清洗的内容
    Returns:
        str: 清洗后的内容
    """
    if not content:
        return ""
    
    # 1. 全小写
    result = content.lower()
    
    # 2. 将所有连续的空白符号（包括空格、换行、制表符等）替换为单个空格
    result = re.sub(r'\s+', ' ', result)
    
    # 去除首尾空格
    result = result.strip()
    
    return result

def is_similarity_query(query1, query2, query_info_dict, similarity_threshold=0.9):
    """
    判断两个query是否相似
    Args:
        query1: 第一个查询
        query2: 第二个查询
        query_info_dict: 存储query信息的字典，格式为 {query: {'embedding': ...}}
        similarity_threshold: 相似度阈值，默认0.7
    Returns:
        bool: 是否相似
    """
    embedding1 = query_info_dict[query1]['embedding']
    embedding2 = query_info_dict[query2]['embedding']
    similarity = simility_tools.cosine_similarity(embedding1, embedding2)
    return similarity > similarity_threshold


def norm_query_by_class(existing_query_dict: Dict[str, Optional[list]], 
                        queries_to_classify: List[str],                        
                        embedding_config_path: str,
                        query_info_dict: Dict[str, Dict[str, Any]] = None,
                        similarity_threshold: float = 0.7,
                        progress_step: int = 1000) -> Dict[str, str]:
    """
    对query进行归一化分类
    Args:
        existing_query_dict: 已有归一化query集合，格式为 {query: embedding}，embedding为None时会自动计算
        queries_to_classify: 待分类的query列表
        embedding_config_path: embedding配置文件路径
        similarity_threshold: 相似度阈值，默认0.7
    Returns:
        Dict[str, str]: 待分类query到归一化query的映射字典
    """
    embedding_obj = embedding_tools.AliEmbedding(embedding_config_path)

    # 准备query_info_dict，用于is_similarity_query函数
    if query_info_dict is None:
        query_info_dict = {}

    def _normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec.astype("float32")
        return (vec / norm).astype("float32")

    # 构建/更新faiss索引的辅助函数
    def _build_faiss_index():
        if not _faiss_available:
            return None, []
        embeddings = []
        id_to_query = []
        for q, info in query_info_dict.items():
            emb = info.get("embedding")
            if emb is None:
                continue
            embeddings.append(_normalize(np.array(emb)))
            id_to_query.append(q)
        if not embeddings:
            return None, []
        dim = embeddings[0].shape[0]
        idx = faiss.IndexFlatIP(dim)
        idx.add(np.vstack(embeddings))
        return idx, id_to_query

    def _faiss_search(index, id_to_query, vec: np.ndarray, topk: int = 3):
        if index is None or index.ntotal == 0:
            return []
        k = min(topk, index.ntotal)
        D, I = index.search(vec.reshape(1, -1).astype("float32"), k)
        res = []
        for ix in I[0]:
            if ix == -1:
                continue
            if ix < len(id_to_query):
                res.append(id_to_query[ix])
        return res

    # 1. 补充已有归一化集合的embedding
    for query in existing_query_dict:
        if existing_query_dict[query] is None:
            if query in query_info_dict:
                existing_query_dict[query] = query_info_dict[query]['embedding']
                continue
            try:
                existing_query_dict[query] = embedding_obj.text2embedding(query)
                
                logging.info(f"计算已有query的embedding: {query}")
            except Exception as e:
                logging.error(f"计算embedding失败 {query}: {e}")
                existing_query_dict[query] = None
        
        # 将已有query加入query_info_dict
        if existing_query_dict[query] is not None:
            query_info_dict[query] = {'embedding': existing_query_dict[query]}

    # 构建初始faiss索引
    faiss_index, id_to_query = _build_faiss_index()

    # 2. 对待分类query进行处理
    result_mapping = {}

    total = len(queries_to_classify)
    for idx, query in enumerate(queries_to_classify, 1):
        if not query or not query.strip():
            continue
            
        query = query.strip()
        
        # 如果query已经在result_mapping中，跳过
        if query in result_mapping:
            continue
        
        # 【关键优化】如果query已经在existing_query_dict中，直接使用，不需要重新分类
        if query in existing_query_dict:
            result_mapping[query] = query
            logging.info(f"直接使用已有归一化query: {query}")
            continue
        
        # 计算query的embedding
        try:
            query_embedding = embedding_obj.text2embedding(query)
            query_info_dict[query] = {'embedding': query_embedding}
        except Exception as e:
            logging.error(f"计算query embedding失败 {query}: {e}")
            # 失败时作为新的归一化query
            existing_query_dict[query] = None
            result_mapping[query] = query
            continue
        
        # 使用faiss检索TOP3候选，再逐个校验
        found_similar = False
        candidates = []
        if _faiss_available and faiss_index is not None and faiss_index.ntotal > 0:
            candidates = _faiss_search(faiss_index, id_to_query, _normalize(np.array(query_embedding)), topk=3)
        else:
            # 回退全量
            candidates = list(existing_query_dict.keys())

        for existing_query in candidates:
            if existing_query in query_info_dict:
                try:
                    if is_similarity_query(query, existing_query, query_info_dict, similarity_threshold):
                        result_mapping[query] = existing_query
                        logging.info(f"归一化映射: {query} -> {existing_query}")
                        found_similar = True
                        break
                except Exception as e:
                    logging.error(f"判断相似度失败 {query} vs {existing_query}: {e}")
                    continue
        
        # 如果没有找到相似的，作为新的归一化query
        if not found_similar:
            existing_query_dict[query] = query_embedding
            result_mapping[query] = query
            logging.info(f"新增归一化query: {query}")
            # 更新索引
            if _faiss_available:
                norm_vec = _normalize(np.array(query_embedding))
                if faiss_index is None:
                    faiss_index = faiss.IndexFlatIP(norm_vec.shape[0])
                    id_to_query = []
                faiss_index.add(norm_vec.reshape(1, -1))
                id_to_query.append(query)

        if progress_step and idx % progress_step == 0:
            logging.info(f"单级归一化进度 {idx}/{total}，当前映射数 {len(result_mapping)}")
    
    return result_mapping


def norm_query_by_user(user_query_dict: Dict[str, List[str]],
                       embedding_config_path: str,
                       similarity_threshold: float = 0.7,
                       existing_query_dict: Optional[Dict[str, Optional[list]]] = None,
                       progress_step: int = 1000,
                       query_info_dict: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, str]:
    """
    按user进行两级query归一化
    Args:
        user_query_dict: 用户query字典，格式为 {user: [query_list]}
        embedding_config_path: embedding配置文件路径
        similarity_threshold: 相似度阈值
        existing_query_dict: 已有的归一化query集合，如果为None则从空开始
    Returns:
        Dict[str, str]: 所有query到最终归一化query的映射
    """
    if query_info_dict is None:
        query_info_dict = {}
    if existing_query_dict is None:
        existing_query_dict = {}
    
    # 第一级：每个user内部的query归一化
    user_first_level_norm_results = {}  # {user: {query: norm_query}}
    user_second_level_norm_results = {}  # {user: {query: norm_query}}
    second_candidate_query_set = set()
    total_users = len(user_query_dict)
    for user_idx, (user, query_list) in enumerate(user_query_dict.items(), 1):
        logging.info(f"开始处理用户 {user} 的 {len(query_list)} 个query")
        
        # 对该user的query进行归一化，使用已有的归一化集合
        user_existing_dict = dict(existing_query_dict)  # 复制一份，避免互相影响
        norm_mapping = norm_query_by_class(
            existing_query_dict=user_existing_dict,
            queries_to_classify=query_list,
            embedding_config_path=embedding_config_path,
            query_info_dict=query_info_dict,
            similarity_threshold=similarity_threshold,
            progress_step=progress_step
        )
        
        user_first_level_norm_results[user] = norm_mapping
        
        # 收集第一级归一化后的所有unique query
        second_candidate_query_set.update(norm_mapping.values())
        if progress_step and user_idx % 10 == 0:
            logging.info(f"第一级归一化用户进度 {user_idx}/{total_users}，累积候选 {len(second_candidate_query_set)}")
    
    logging.info(f"第一级归一化完成，共得到 {len(second_candidate_query_set)} 个归一化query")
    
    # 第二级：对所有第一级归一化后的query再次归一化
    logging.info("开始第二级归一化")
    second_level_mapping = norm_query_by_class(
        existing_query_dict=existing_query_dict,
        queries_to_classify=list(second_candidate_query_set),
        embedding_config_path=embedding_config_path,
        query_info_dict=query_info_dict,
        similarity_threshold=similarity_threshold,
        progress_step=progress_step
    )
    
    # 构建最终映射：原始query -> 最终归一化query
    final_mapping = {}
    for user, first_level_mapping in user_first_level_norm_results.items():
        for original_query, first_norm in first_level_mapping.items():
            final_norm = second_level_mapping.get(first_norm, first_norm)        
            final_mapping[original_query] = final_norm
            logging.debug(f"最终映射 [{user}]: {original_query} -> {first_norm} -> {final_norm}")
    logging.info(f"二级归一化完成，共有 {len(final_mapping)} 个原始query，归一到 {len(set(final_mapping.values()))} 个归一化query")
    
    return final_mapping


def norm_query_file(input_file, output_file, similarity_config, query_field=0, similarity_threshold=0.7):
    """
    将相似查询归一化到代表查询
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径 
        similarity_config: 相似度配置
        query_field: query在行中的位置
        similarity_threshold: 相似度阈值，默认0.7
    """
    embedding_obj = embedding_tools.AliEmbedding(similarity_config)
    cluster_dict = {}  # 存储查询簇，key为代表query
    query_info_dict = {}  # 存储query信息，包含embedding等
    
    with open(input_file, 'r', encoding='utf-8') as fin, \
         open(output_file, 'w', encoding='utf-8') as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) <= query_field:
                continue
                
            query = fields[query_field]
            
            # 如果是新query，计算embedding并进行聚类
            if query not in query_info_dict:
                query_info_dict[query] = {
                    'embedding': embedding_obj.text2embedding(query)
                }
                
                # 寻找相似簇
                found_cluster = False
                for rep_query in cluster_dict:
                    if is_similarity_query(query, rep_query, query_info_dict, similarity_threshold):
                        cluster_dict[rep_query].append(query)
                        found_cluster = True
                        break
                
                # 如果没找到相似簇，创建新簇
                if not found_cluster:
                    cluster_dict[query] = [query]
            
            # 找到归一化后的query
            norm_query = None
            for rep_query, cluster in cluster_dict.items():
                if query in cluster:
                    norm_query = rep_query
                    break
            
            # 输出结果
            fields.insert(query_field + 1, norm_query)
            fout.write('\t'.join(fields) + '\n')


if __name__ == '__main__':
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.INFO, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )    
    
    fire.Fire({
        'norm_query_file': norm_query_file,
    })

