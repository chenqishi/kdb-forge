"""
Mercado Livre knowledge-hub 特殊页面解析器

用于从嵌入式前端状态 JSON 中提取子页面链接。
knowledge-hub 页面的子链接不以 <a href> 形式存在于 HTML 中，
而是嵌入在 _n.ctx.s.q("...") 的 JSON 状态里，通过 children_data 数组承载。

URL pattern: https://www.mercadolivre.com.br/knowledge-hub/{id}
"""

import re
import logging
from urllib.parse import urlparse


# knowledge-hub URL pattern，匹配 mercadolivre / mercadolibre 等域名
KNOWLEDGE_HUB_URL_PATTERN = re.compile(
    r'https?://[^/]*mercadoli[^/]*/knowledge-hub/\d+'
)


def is_knowledge_hub_url(url):
    """
    判断URL是否为 knowledge-hub 类型

    Args:
        url: 待检测的URL

    Returns:
        bool: 是否匹配 knowledge-hub pattern
    """
    return bool(KNOWLEDGE_HUB_URL_PATTERN.match(url))


def extract_knowledge_hub_children(html_content, current_url):
    """
    从 knowledge-hub 页面的 HTML 中提取子页面 URL。

    子页面数据嵌入在前端状态 JSON 中，格式为:
    _n.ctx.s.q("{...\"children_data\":[{\"id\":669,...},...]...}")

    通过正则匹配 children_data 数组，提取每个子项的 id，
    然后拼接为完整的 knowledge-hub URL。

    Args:
        html_content: HTML 页面内容
        current_url: 当前页面 URL

    Returns:
        list[dict]: 子页面信息列表，每项包含 'url' 和 'title'
    """
    if not is_knowledge_hub_url(current_url):
        return []

    # 提取 base URL: scheme + netloc + /knowledge-hub
    parsed = urlparse(current_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}/knowledge-hub"

    children = []

    try:
        # 在 HTML 中查找 children_data 数组
        # 引号可能有多层转义: "、\"、\\\"、\\\\" 等，用 \\* 匹配任意数量的反斜杠
        children_data_pattern = re.compile(
            r'\\*"children_data\\*"\s*:\s*\[(.+?)\]',
            re.DOTALL
        )
        match = children_data_pattern.search(html_content)

        if not match:
            logging.info(f"未在页面 {current_url} 中找到 children_data")
            return []

        children_str = match.group(1)

        # 按 },{ 分割为各个子对象字符串（保留花括号内容）
        child_items = re.split(r'\},\s*\{', children_str)
        id_pattern = re.compile(r'\\*"id\\*"\s*:\s*(\d+)')
        title_pattern = re.compile(r'\\*"title\\*"\s*:\s*\\*"(.+?)\\*"')

        for item_str in child_items:
            id_match = id_pattern.search(item_str)
            if not id_match:
                continue

            child_id = id_match.group(1)
            child_url = f"{base_url}/{child_id}"

            title_match = title_pattern.search(item_str)
            child_title = title_match.group(1) if title_match else ''
            # 清理 title 中的转义字符
            child_title = re.sub(r'\\+', '', child_title)

            children.append({
                'url': child_url,
                'title': child_title
            })
            logging.info(
                f"提取到 knowledge-hub 子链接: {child_url} (title: {child_title})"
            )

        logging.info(
            f"从 {current_url} 共提取到 {len(children)} 个 knowledge-hub 子链接"
        )

    except Exception as e:
        logging.error(
            f"从 {current_url} 提取 knowledge-hub 子链接失败: {e}"
        )

    return children
