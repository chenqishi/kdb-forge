import re
import logging
from typing import List, Tuple
try:
    from rapidfuzz.distance import Levenshtein
except:
    Levenshtein = None

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

def construct_multimodel_undestanding_content(content, url_process_result):
    """
    构造多媒体理解内容
    
    Args:
        content: 文本内容
        url_process_result: 链接处理结果，字典格式，key 为content中的 URL，value 为 process_one_data 返回的结果
            结果格式包含：
            - public_url: 内部链接（处理后的 URL）
            - image_understanding: 图片理解内容
            - image_ocr: OCR 内容
            - is_valid: 是否有效
    
    Returns:
        str: 处理后的内容，原始 URL 替换为 markdown 格式，并追加 OCR 和图片理解内容
    """
    if not content or not isinstance(content, str):
        return content or ""
    
    if not url_process_result or not isinstance(url_process_result, dict):
        return content
    
    result_content = content
    
    # 按照 URL 长度降序排序，避免短 URL 替换长 URL 的一部分
    sorted_urls = sorted(url_process_result.items(), key=lambda x: len(x[0]), reverse=True)
    
    for original_url, process_result in sorted_urls:
        if not isinstance(process_result, dict):
            continue
        
        # 获取处理结果
        public_url = process_result.get("public_url")
        image_ocr = process_result.get("image_ocr")
        image_understanding = process_result.get("image_understanding")
        is_valid = process_result.get("is_valid", False)
        
        # 如果无效或没有 public_url，跳过
        if not is_valid or not public_url:
            continue
        
        # 在 content 中查找原始 URL
        if original_url not in result_content:
            continue
        
        # 构建 markdown 格式的图片链接
        markdown_image = f'![嵌入图片]({public_url} "Flowchart")'
        
        # 构建追加内容
        append_content_parts = []
        
        # 添加 OCR 内容
        if image_ocr:
            append_content_parts.append(f'{public_url}的ocr理解为:\n<image_ocr>{image_ocr}</image_ocr>')
        
        # 添加图片理解内容
        if image_understanding:
            append_content_parts.append(f'{public_url}的图片理解为:\n<image_understanding>{image_understanding}</image_understanding>')
        
        # 将原始 URL 替换为 markdown 格式 + 追加内容
        if append_content_parts:
            replacement = f'{markdown_image}\n' + '\n'.join(append_content_parts)
        else:
            replacement = markdown_image
        
        # 替换所有出现的原始 URL
        result_content = result_content.replace(original_url, replacement)
    
    return result_content




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