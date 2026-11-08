import logging
logger = logging.getLogger('kdb.entrypoints.http.multilingual.app')

def has_hiragana_or_katakana(text):
    """检测文本是否包含日文假名（ひらがな、カタカナ）"""
    # ひらがな（平假名）: \u3040-\u309F
    # カタカナ（片假名）: \u30A0-\u30FF
    for char in text:
        if '\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF':
            return True
    return False


def has_hangul(text):
    """检测文本是否包含韩文（Hangul）"""
    # Hangul: \uAC00-\uD7AF
    for char in text:
        if '\uAC00' <= char <= '\uD7AF':
            return True
    return False


def mostly_cjk(text):
    """检测文本是否80%以上是汉字（CJK）"""
    if not text:
        return False

    # CJK统一汉字范围: \u4E00-\u9FFF
    # CJK扩展A区: \u3400-\u4DBF
    cjk_count = 0
    total_chars = 0

    for char in text:
        # 统计所有字符（包括空格、标点等）
        total_chars += 1
        # 检查是否是CJK字符
        if '\u4E00' <= char <= '\u9FFF' or '\u3400' <= char <= '\u4DBF':
            cjk_count += 1

    if total_chars == 0:
        return False

    # 计算CJK字符占比
    cjk_ratio = cjk_count / total_chars
    return cjk_ratio >= 0.8


def rule_based_language_detection(text):
    """
    基于规则的语言检测
    返回: (label, confidence) 或 None（如果规则无法判断）
    label格式: __label__xx
    """
    # 若文本够长，则不进行规则判断，因为模型判断会更准确
    if len(text) > 100:
        return None
    # 规则1: 如果包含日文假名，判断为日语
    if has_hiragana_or_katakana(text):
        logger.info(f"规则判断: 检测到日文假名，判断为日语")
        return ('__label__ja', 1.0)

    # 规则2: 如果包含韩文，判断为韩语
    if has_hangul(text):
        logger.info(f"规则判断: 检测到韩文，判断为韩语")
        return ('__label__ko', 1.0)

    # 规则3: 如果80%以上是CJK且没有日文假名和韩文，判断为中文
    if mostly_cjk(text):
        logger.info(f"规则判断: 检测到80%以上CJK字符，判断为中文")
        return ('__label__zh', 1.0)

    # 规则无法判断，返回None
    return None
