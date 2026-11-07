import jieba.analyse
import numpy as np
from typing import List, Dict, Tuple

def normalize_scores(word_scores: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    """
    归一化关键词得分
    Args:
        word_scores: 关键词和得分列表 [(word, score),...]
    Returns:
        List[Tuple[str, float]]: 归一化后的关键词和得分列表
    """
    if not word_scores:
        return []
    scores = np.array([score for _, score in word_scores])
    min_score = scores.min()
    max_score = scores.max()
    if max_score == min_score:
        normalized_scores = np.ones_like(scores)
    else:
        normalized_scores = (scores - min_score) / (max_score - min_score)
    return [(word, float(score)) for (word, _), score in zip(word_scores, normalized_scores)]

def merge_keywords(title_keywords: List[Tuple[str, float]], 
                  content_keywords: List[Tuple[str, float]], 
                  title_weight: float = 0.7,
                  content_weight: float = 0.3) -> List[Tuple[str, float]]:
    """
    合并title和content的关键词
    Args:
        title_keywords: title的关键词和得分列表
        content_keywords: content的关键词和得分列表
        title_weight: title关键词的权重
        content_weight: content关键词的权重
    Returns:
        List[Tuple[str, float]]: 合并后的关键词和得分列表
    """
    # 创建关键词得分字典
    word_scores = {}
    
    # 处理title关键词
    for word, score in title_keywords:
        word_scores[word] = score * title_weight
    
    # 处理content关键词
    for word, score in content_keywords:
        if word in word_scores:
            word_scores[word] += score * content_weight
        else:
            word_scores[word] = score * content_weight
    
    # 转换为列表并排序
    merged_keywords = [(word, score) for word, score in word_scores.items()]
    merged_keywords.sort(key=lambda x: x[1], reverse=True)
    
    return merged_keywords

def gen_keyword_by_title_content(title: str, content: str, topK: int = 5) -> List[Dict[str, float]]:
    """
    根据标题和内容生成关键词
    Args:
        title: 标题
        content: 内容
        topK: 保留的关键词数量
    Returns:
        List[Dict[str, float]]: 关键词列表，每个关键词包含word和score
    """
    # 1. 分别提取title和content的关键词
    title_keywords = jieba.analyse.textrank(title, topK=topK, withWeight=True) if title else []
    content_keywords = jieba.analyse.textrank(content, topK=topK, withWeight=True) if content else []
    
    # 2. 归一化得分
    title_keywords = normalize_scores(title_keywords)
    content_keywords = normalize_scores(content_keywords)
    
    # 3. 合并关键词并计算最终得分
    merged_keywords = merge_keywords(title_keywords, content_keywords)
    
    # 4. 选择最终的关键词
    final_keywords = []
    high_score_keywords = [(word, score) for word, score in merged_keywords if score >= 0.8]
    
    # 如果高分关键词不够，则补充其他关键词
    if len(high_score_keywords) < topK:
        remaining_keywords = [(word, score) for word, score in merged_keywords 
                            if (word, score) not in high_score_keywords]
        high_score_keywords.extend(remaining_keywords[:topK - len(high_score_keywords)])
    
    # 5. 转换为指定格式
    for word, score in high_score_keywords[:topK]:
        final_keywords.append({
            "word": word,
            "score": float(score)
        })
    
    return final_keywords
