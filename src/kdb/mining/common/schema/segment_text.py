import re

def parse_segment(text, use_keywords=True):
    # 提取正文内容

    # 提取关键词
    keyword_match = re.search(r'-.*?关键词：(.*?)\n', text)
    keywords = keyword_match.group(1).strip() if keyword_match else None

    # 提取图谱标签
    label_match = re.search(r'-.*?图谱标签: (.*?)\n', text)
    label = label_match.group(1).strip() if label_match else None

    # 提取属性
    attribute_match = re.search(r'-.*?属性：(.*?)$', text)
    attribute = attribute_match.group(1).strip() if attribute_match else None
    content = re.sub(r'-.*?关键词：.*?\n', '', text)
    content = re.sub(r'-.*?图谱标签: .*?\n', '', content)
    content = re.sub(r'-.*?属性：.*?$', '', content)
    keywords = re.split(r'、|,|\ ', keywords) if keywords else []
    if use_keywords:
        return {
            'content': content,
            'keywords': keywords,
            'label': label,
            'attribute': attribute
        }
    else:
        return {
            'content': content,
            'label': label,
            'attribute': attribute
        }
