from commons import embedding_tools
from commons import simility_tools

def norm_query_file(input_file, output_file, similarity_config, query_field=0):
    """
    将相似查询归一化到代表查询
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径 
        similarity_config: 相似度配置
        query_field: query在行中的位置
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
                    if is_similarity_query(query, rep_query, query_info_dict):
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

def is_similarity_query(query1, query2, query_info_dict):
    """
    判断两个query是否相似
    Args:
        query1: 第一个查询
        query2: 第二个查询
        query_info_dict: 存储query信息的字典
    Returns:
        bool: 是否相似
    """
    embedding1 = query_info_dict[query1]['embedding']
    embedding2 = query_info_dict[query2]['embedding']
    similarity = simility_tools.cosine_similarity(embedding1, embedding2)
    return similarity > 0.7  # 可以根据需要调整阈值

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