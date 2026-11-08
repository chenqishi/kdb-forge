import numpy as np

def cosine_similarity(vec1, vec2):
    """
    计算两个向量的余弦相似度
    :param vec1: 向量1
    :param vec2: 向量2
    :return: 相似度分数 (0-1之间)
    """
    if isinstance(vec1, list):
        vec1 = np.array(vec1)
    if isinstance(vec2, list):
        vec2 = np.array(vec2)

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0

    return np.dot(vec1, vec2) / (norm1 * norm2)
