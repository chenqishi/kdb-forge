from typing import List
from typing import Tuple
import logging
import re

def text_segment_by_limit(text, len_limit=2000, sep=None, overlap_num=1):
    """
    将文本按照长度限制和分隔符进行分段，并生成带有重叠的段落
    
    Args:
        text (str): 待分段的文本
        len_limit (int): 每段文本的最大长度限制
        sep (str/list): 分隔符，可以是单个字符串或字符串列表(支持多字符)，默认使用 ['。', '！', '？', '.', '!', '?', '\n']
        overlap_num (int): 重叠的句子数量
        
    Returns:
        tuple: (origin_segments, overlap_segments)
            - origin_segments: 原始分段列表
            - overlap_segments: 带有重叠的分段列表
    """
    if not text:
        return [], []
        
    # 构建分隔符正则
    if sep is None:
        sep_pattern = r'(?:。|！|？|\.|\!|\?|\n)+'
    else:
        # 将分隔符列表转换为正则表达式
        if isinstance(sep, list):
            sep_pattern = f"(?:{'|'.join(map(re.escape, sep))})"
        else:
            sep_pattern = re.escape(sep)
    
    # 使用re.split进行分句，保留分隔符
    splits = re.split(f'({sep_pattern})', text)
    # 将分句和分隔符组合，去除空字符串
    sentences = [''.join(pair) for pair in zip(splits[::2], splits[1::2] + ['']) if pair[0].strip()]
    logging.info(f"分句后句子数量: {len(sentences)}")
    # 同时生成原始分段和重叠分段
    origin_segments = []
    overlap_segments = []
    current_segment = []
    current_length = 0
    start_index = 0
    for i, sentence in enumerate(sentences):
        sentence_len = len(sentence)
        
        # 如果当前段落加上新句子超过长度限制，需要开始新的段落
        
        if current_length + sentence_len > len_limit and current_segment:
            # 保存原始段落
            end_index = i
            logging.info(f"当前段落结束索引: start_index={start_index}, end_index={end_index}")
            origin_segments.append(''.join(sentences[start_index: end_index]))
            
            # 构建重叠段落
            overlap_text = []
            # 添加前overlap_num个句子
            if len(origin_segments) > 1:
                prev_start = max(0, start_index - overlap_num)
                overlap_text.extend(sentences[prev_start: start_index])
            
            # 添加当前段落
            overlap_text.extend(current_segment)
            
            if i <= len(sentences) - 1:
                post_end = min(i + overlap_num, len(sentences))
                # 添加后overlap_num个句子
                next_sentences = sentences[i: post_end]
                overlap_text.extend(next_sentences)
            
            overlap_segments.append(''.join(overlap_text))
            
            # 开始新的段落
            current_segment = [sentence]
            current_length = sentence_len
            start_index = i
        else:
            current_segment.append(sentence)
            current_length += sentence_len
    
    # 处理最后一个段落
    if current_segment:
        origin_segments.append(''.join(current_segment))
        
        # 构建最后一个重叠段落
        overlap_text = []
        if len(origin_segments) > 1:
            prev_sentences = sentences[-overlap_num-len(current_segment):-len(current_segment)]
            overlap_text.extend(prev_sentences)
        overlap_text.extend(current_segment)
        overlap_segments.append(''.join(overlap_text))
    
    return origin_segments, overlap_segments


def cluster_by_edit_distance(
        words: List[str],
        max_abs_distance: int = 2,
        max_ratio: float = 0.3,
        normalize: bool = True
    ) -> Tuple[List[List[str]], int]:

    if not words:
        return [], 0

    # 规范化
    norm_words = []
    for w in words:
        t = w.strip()
        if normalize:
            t = t.lower()
        norm_words.append(t)

    clusters: List[List[str]] = []
    centers: List[str] = []

    for orig, norm in zip(words, norm_words):
        if not norm:
            clusters.append([orig])
            centers.append(norm)
            continue

        placed = False

        for idx, center in enumerate(centers):
            # 动态距离阈值
            L = min(len(norm), len(center))
            allowed = max(max_abs_distance, int(L * max_ratio))

            d = Levenshtein.distance(norm, center)

            if d <= allowed:
                clusters[idx].append(orig)
                placed = True
                break

        if not placed:
            clusters.append([orig])
            centers.append(norm)

    return clusters, len(clusters)


try:
    from rapidfuzz.distance import Levenshtein
except:
    Levenshtein = None
